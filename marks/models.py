import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone


TELEGRAM_LINK_DOMAIN = "https://telegram.me"


def task_request_photo_upload_to(instance, filename):
    extension = Path(filename or "").suffix.lower() or ".bin"
    return f"task_request_photos/{timezone.now():%Y/%m/%d}/{uuid4().hex}{extension}"


class Product(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.name


class Bot(models.Model):
    class Platform(models.TextChoices):
        TELEGRAM = "tg", "Telegram"
        VK = "vk", "VK"

    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="bots")
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.TELEGRAM)
    name = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    salebot_url = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


    def __str__(self):
        return self.title

    @property
    def api_name(self):
        return (self.name or "").strip()

    @property
    def title(self):
        return (self.display_name or self.api_name).strip()

    @property
    def ui_identifier(self):
        identifier = self.api_name.lstrip("@")
        if self.platform == self.Platform.VK:
            return identifier
        return f"@{identifier}" if identifier else ""

    @property
    def sort_key(self):
        return (self.title or self.api_name).casefold()

    @property
    def platform_order(self):
        order = {
            self.Platform.TELEGRAM: 0,
            self.Platform.VK: 1,
        }
        return order.get(self.platform, 99)

    def build_tag_url(self, tag_number, ref_source=None):
        tag_number = str(tag_number or "").strip()
        identifier = self.api_name.lstrip("@")
        if self.platform == self.Platform.VK:
            params = {"ref": tag_number}
            if ref_source not in {None, ""}:
                params["ref_source"] = str(ref_source)
            return f"https://vk.com/write-{identifier}?{urlencode(params)}"
        return f"{TELEGRAM_LINK_DOMAIN}/{identifier}?start={tag_number}"


class PlanMonthly(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="plans")
    month = models.DateField(help_text="Первое число месяца (YYYY-MM-01)")


    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    revenue_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warm_leads_target = models.IntegerField(default=0)
    cold_leads_target = models.IntegerField(default=0)
    notes = models.TextField(blank=True)


    class Meta:
        unique_together = ("product", "month")
        ordering = ["-month"]


    def __str__(self):
        return f"{self.product} · {self.month:%Y-%m}"


class BranchPlanMonthly(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="plans")
    month = models.DateField()
    warm_leads = models.IntegerField(default=0)
    cold_leads = models.IntegerField(default=0)
    expected_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    comment = models.CharField(max_length=255, blank=True)


    class Meta:
        unique_together = ("branch", "month")
        ordering = ["branch__bot__name", "branch__name", "-month"]


    def __str__(self):
        return f"{self.branch} · {self.month:%Y-%m}"


class Funnel(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="funnels")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("product", "name")


    def __str__(self):
        return f"{self.product} · {self.name}"


class TrafficReport(models.Model):
    class Platform(models.TextChoices):
        TG = "tg", "Telegram"
        VK = "vk", "VK"
        TIKTOK = "tt", "TikTok"
        INST = "ig", "Instagram"
        OTHER = "other", "Другое"


    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="traffic_reports")
    month = models.DateField()
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.OTHER)
    vendor = models.CharField(max_length=255, help_text="Подрядчик/исполнитель")
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    leads_warm = models.IntegerField(default=0)
    leads_cold = models.IntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)


    class Meta:
        ordering = ["-month", "platform", "vendor"]


class PatchNote(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="patch_notes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    change_description = models.TextField()


    change_type = models.CharField(max_length=50, default="update", help_text="например: план, метки, воронка, отчёт")


    class Meta:
        ordering = ["-created_at"]


    def __str__(self):
        return f"{self.branch} · {self.title}"


class Branch(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("bot", "code")

    @classmethod
    def suggest_next_code(cls, bot):
        if bot is None:
            return ""

        grouped_codes = {}
        for code in cls.objects.filter(bot=bot).values_list("code", flat=True):
            match = re.match(r"^(.*?)(\d+)$", (code or "").strip())
            if not match:
                continue

            prefix, number = match.groups()
            width = len(number)
            grouped_codes.setdefault((prefix, width), []).append(int(number))

        if not grouped_codes:
            return ""

        (prefix, width), numbers = max(
            grouped_codes.items(),
            key=lambda item: (len(item[1]), max(item[1]), item[0][0].casefold()),
        )
        return f"{prefix}{max(numbers) + 1:0{width}d}"

    @property
    def ref_source(self):
        match = re.search(r"(\d+)$", (self.code or "").strip())
        if not match:
            return None
        return str(int(match.group(1)))


    def __str__(self):
        return f"{self.bot.title} - {self.name} ({self.code})"


class TaskRequest(models.Model):
    class Type(models.TextChoices):
        PATCH = "patch", "Правка в ветках бота"
        MAILING = "mailing", "Рассылка"
        BUILD = "build", "Сборка бота"

    class Status(models.TextChoices):
        UNREAD = "unread", "Непрочитанное"
        IN_PROGRESS = "in_progress", "В процессе"
        DONE = "done", "Готово"

    task_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNREAD)
    branches = models.ManyToManyField(Branch, related_name="task_requests", blank=True)

    cjm_url = models.URLField(blank=True, default="")
    tz_url = models.URLField(blank=True, default="")
    build_name = models.CharField(max_length=255, blank=True, default="")
    build_token = models.CharField(max_length=255, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    photo = models.FileField(upload_to=task_request_photo_upload_to, blank=True, default="")
    deadline = models.DateTimeField()

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.id} {self.get_task_type_display()}"

    def save(self, *args, **kwargs):
        auto_completed_at = False
        if self.status == self.Status.DONE and self.completed_at is None:
            self.completed_at = timezone.now()
            auto_completed_at = True
        elif self.status != self.Status.DONE and self.completed_at is not None:
            self.completed_at = None
        super().save(*args, **kwargs)
        if auto_completed_at and self.status == self.Status.DONE and self.created_at and self.completed_at and self.completed_at < self.created_at:
            self.completed_at = self.created_at
            type(self).objects.filter(pk=self.pk).update(completed_at=self.created_at, updated_at=timezone.now())

    @staticmethod
    def _bot_branch_label(branch):
        bot_name = (getattr(getattr(branch, "bot", None), "title", "") or "").strip()
        branch_name = (getattr(branch, "name", "") or "").strip()
        if not bot_name:
            return ""
        if not branch_name or branch_name.lower() == "main":
            return bot_name
        normalized_branch = "_".join(branch_name.split())
        return f"{bot_name}_{normalized_branch}"

    def get_bot_branch_labels(self):
        labels = []
        seen = set()
        for branch in self.branches.select_related("bot").all():
            label = self._bot_branch_label(branch)
            if label and label not in seen:
                labels.append(label)
                seen.add(label)
        if labels:
            return labels

        raw = (self.build_name or "").strip()
        if not raw:
            return []
        fallback = []
        for part in raw.split(","):
            value = part.strip()
            if value and value not in seen:
                fallback.append(value)
                seen.add(value)
        return fallback

    def get_bot_branch_text(self):
        labels = self.get_bot_branch_labels()
        if not labels:
            return "-"
        return ", ".join(labels)

    def get_scope_units(self):
        if self.task_type not in {self.Type.PATCH, self.Type.MAILING, self.Type.BUILD}:
            return 0
        labels = self.get_bot_branch_labels()
        if labels:
            return len(labels)
        return 1


class Experiment(models.Model):
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Подготовка"
        DRAFT = "draft", "Разработка"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершен"
        SUCCESS = "success", "Успех"
        FAILED = "failed", "Провал"
        RETEST = "retest", "Нужен ретест"

    class TrafficVolume(models.TextChoices):
        SPLIT_50_50 = "50_50", "50/50"
        SPLIT_70_30 = "70_30", "70/30"
        PART_OF_BASE = "part_of_base", "Только часть базы"
        OTHER = "other", "Другое"

    class TestDuration(models.TextChoices):
        DAYS_3 = "3_days", "3 дня"
        DAYS_7 = "7_days", "7 дней"
        UNTIL_USERS = "until_users", "До набора X пользователей"
        END_DATE = "end_date", "Конкретная дата окончания"

    CUSTOM_SPLIT_RE = re.compile(r"^\s*(\d{1,3})\s*[/:\-]\s*(\d{1,3})\s*$")

    title = models.CharField(max_length=255, blank=True, default="")
    branch = models.ForeignKey("Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="experiments")
    wants_ab_test = models.BooleanField(default=False)
    ab_test_options = models.JSONField(blank=True, default=list)
    ab_test_custom_option = models.CharField(max_length=255, blank=True, default="")
    metric_impact = models.CharField(max_length=255, blank=True, default="")
    comparison_text = models.CharField(max_length=255, blank=True, default="")
    expected_change = models.CharField(max_length=255, blank=True, default="")
    hypothesis = models.TextField(blank=True, default="")
    tz_url = models.CharField(max_length=500, blank=True, default="")
    traffic_volume = models.CharField(max_length=20, choices=TrafficVolume.choices, blank=True, default="")
    traffic_volume_other = models.CharField(max_length=255, blank=True, default="")
    test_duration = models.CharField(max_length=20, choices=TestDuration.choices, blank=True, default="")
    duration_users = models.PositiveIntegerField(null=True, blank=True)
    duration_end_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    dashboard_url = models.CharField(max_length=500, blank=True, default="")
    result_variant_a = models.TextField(blank=True, default="")
    result_variant_b = models.TextField(blank=True, default="")
    comment = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BACKLOG)
    technical_task = models.ForeignKey(
        TaskRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_experiments",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        name = self.title or f"Эксперимент #{self.id}"
        return f"{name} ({self.get_status_display()})"

    @classmethod
    def parse_traffic_split(cls, traffic_volume, traffic_volume_other=""):
        predefined = {
            cls.TrafficVolume.SPLIT_50_50: (50, 50),
            cls.TrafficVolume.SPLIT_70_30: (70, 30),
        }
        if traffic_volume in predefined:
            return predefined[traffic_volume]
        if traffic_volume != cls.TrafficVolume.OTHER:
            return None

        match = cls.CUSTOM_SPLIT_RE.match((traffic_volume_other or "").strip())
        if not match:
            return None

        left = int(match.group(1))
        right = int(match.group(2))
        if left <= 0 or right <= 0:
            return None
        return left, right

    def get_traffic_split_weights(self):
        return self.parse_traffic_split(self.traffic_volume, self.traffic_volume_other)

    def is_api_active(self, current_date=None):
        if not self.wants_ab_test or self.status != self.Status.IN_PROGRESS or not self.branch_id:
            return False
        if self.get_traffic_split_weights() is None:
            return False

        current_date = current_date or timezone.localdate()
        if self.start_date and self.start_date > current_date:
            return False
        if self.end_date and self.end_date < current_date:
            return False
        return True


class Tag(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="tags")
    number = models.CharField(max_length=20, blank=True)
    utm_source = models.CharField(max_length=255, blank=True, null=True)
    utm_medium = models.CharField(max_length=255, blank=True, null=True)
    utm_campaign = models.CharField(max_length=255, blank=True, null=True)
    utm_term = models.CharField(max_length=255, blank=True, null=True)
    utm_content = models.CharField(max_length=255, blank=True, null=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True, blank=True, verbose_name="Бюджет")
    url = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("branch", "number")
        ordering = ["number"]


    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if not self.number:
            prefix = self.branch.code
            last_tag = Tag.objects.filter(branch=self.branch).order_by("-number").first()
            if last_tag:
                last_num = int(last_tag.number.replace(prefix, ""))
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = "0001"
            self.number = f"{prefix}{new_num}"

        self.url = self.branch.bot.build_tag_url(self.number, self.branch.ref_source)
        if update_fields is not None:
            normalized_update_fields = set(update_fields)
            normalized_update_fields.add("url")
            kwargs["update_fields"] = list(normalized_update_fields)


        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.number} ({self.branch})"


@receiver(post_save, sender=Branch)
def create_first_tag(sender, instance, created, **kwargs):
    if created and not instance.tags.exists():
        Tag.objects.create(branch=instance)


class TikTokFunnelRequest(models.Model):
    """Marketer's intake for a new TikTok funnel.

    Marketer fills endpoint/offer/bot; a developer later connects pixel + token
    on the warehouse side and flips the funnel to ``active``. This record is the
    automarks-side source of truth for the request; on creation a matching draft
    row (status=pending) is provisioned into ``activation_data.tt_funnels`` on the
    warehouse via marks.services.funnels.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подключения"
        ACTIVE = "active", "Активна"

    landing_endpoint = models.CharField(
        max_length=255,
        unique=True,
        help_text="location.pathname лендинга, например /pasha_all",
    )
    offer = models.CharField(max_length=255, help_text="Оффер/метка, например ell010005")
    bot_url = models.CharField(max_length=500, help_text="Ссылка на бота")
    bot_name = models.CharField(max_length=255, blank=True, default="")
    pixel_code = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    comment = models.TextField(blank=True, default="")
    warehouse_synced = models.BooleanField(
        default=False,
        help_text="Черновик воронки успешно записан в activation_data.tt_funnels",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.landing_endpoint} ({self.get_status_display()})"

    @staticmethod
    def normalize_endpoint(raw):
        """Reduce any user input to a bare ``/path`` matching location.pathname.

        Strips scheme/domain, query and fragment, collapses a trailing slash and
        guarantees a single leading slash. This must match what the landing
        script writes into visits_data.landing_endpoint, otherwise the warehouse
        JOIN never matches.
        """
        value = (raw or "").strip()
        if not value:
            return ""

        if "://" in value:
            value = urlsplit(value).path
        else:
            # Drop a leading bare domain like "go-egeland.ru/pasha_all".
            head = value.split("/", 1)[0]
            if "." in head and " " not in head:
                value = urlsplit("//" + value).path
            else:
                # Strip a stray query/fragment even without a domain.
                value = value.split("?", 1)[0].split("#", 1)[0]

        value = value.strip()
        if not value:
            return ""
        if not value.startswith("/"):
            value = "/" + value
        if len(value) > 1:
            value = "/" + value.strip("/")
        return value

    @staticmethod
    def parse_bot_name(bot_url):
        """Extract a bare bot identifier from a bot link.

        ``https://telegram.me/efir_tt_el_bot`` -> ``efir_tt_el_bot``; tolerates a
        trailing slash, query string and ``@``/``+`` prefixes.
        """
        raw = (bot_url or "").strip()
        if not raw:
            return ""
        path = urlsplit(raw if "://" in raw else "//" + raw).path
        segment = path.rstrip("/").rsplit("/", 1)[-1]
        return segment.lstrip("@+").strip()


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Максимальный"
        MANAGER = "manager", "Руководитель"
        MARKETER = "marketer", "Линейный (автометки)"
        BOT_USER = "bot_user", "Оператор ботов"


    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MARKETER)


    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
