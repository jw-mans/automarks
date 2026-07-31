from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from pathlib import Path
import re

from .models import (
    Bot,
    Branch,
    BranchPlanMonthly,
    Experiment,
    Funnel,
    PatchNote,
    PlanMonthly,
    Product,
    Tag,
    TaskRequest,
    TikTokFunnelRequest,
    TrafficReport,
)
from .task_time import TASK_INPUT_FORMATS, parse_task_input_datetime


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "is_active"]


class PlanMonthlyForm(forms.ModelForm):
    class Meta:
        model = PlanMonthly
        fields = ["product", "month", "budget", "revenue_target", "warm_leads_target", "cold_leads_target", "notes"]


class BranchPlanMonthlyForm(forms.ModelForm):
    class Meta:
        model = BranchPlanMonthly
        fields = ["branch", "month", "warm_leads", "cold_leads", "expected_revenue", "comment"]


class FunnelForm(forms.ModelForm):
    class Meta:
        model = Funnel
        fields = ["product", "name", "description", "is_active"]


class FunnelMasterForm(forms.Form):
    TYPE_CHOICES = (
        ("funnel", "Воронка"),
        ("bot", "Бот"),
    )
    type = forms.ChoiceField(choices=TYPE_CHOICES, initial="funnel", label="Тип")
    product = forms.ModelChoiceField(queryset=Product.objects.all(), label="Продукт", required=False)
    name = forms.CharField(max_length=255, label="Название")
    description = forms.CharField(required=False, widget=forms.Textarea, label="Описание")
    is_active = forms.BooleanField(required=False, initial=True, label="Активна")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("type") == "funnel" and not cleaned.get("product"):
            self.add_error("product", "Выберите продукт для воронки.")
        return cleaned


class TrafficReportForm(forms.ModelForm):
    class Meta:
        model = TrafficReport
        fields = ["product", "month", "platform", "vendor", "spend", "impressions", "clicks", "leads_warm", "leads_cold", "notes"]


class PatchNoteForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Текст",
    )
    created_at = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата",
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Ветки",
    )

    def __init__(self, *args, branches=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branches is None:
            branches = Branch.objects.all()
        self.fields["branches"].queryset = branches


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class BotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Username бота"
        self.fields["name"].widget.attrs["placeholder"] = "@new_bot"

    def clean_name(self):
        value = " ".join((self.cleaned_data.get("name") or "").strip().split())
        value = value.lstrip("@")
        if not value:
            raise forms.ValidationError("Укажите username бота.")
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", value) is None:
            raise forms.ValidationError("Username Telegram должен содержать 5-32 символа: буквы, цифры и _.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.platform = Bot.Platform.TELEGRAM
        obj.display_name = ""
        if commit:
            obj.save()
        return obj


class VKBotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["name", "display_name"]
        labels = {
            "name": "ID группы",
            "display_name": "Название",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = "203482421"
        self.fields["display_name"].widget.attrs["placeholder"] = "VK бот курса"

    def clean_name(self):
        value = "".join((self.cleaned_data.get("name") or "").split())
        if not value:
            raise forms.ValidationError("Укажите ID группы VK.")
        if re.fullmatch(r"\d{3,32}", value) is None:
            raise forms.ValidationError("ID группы VK должен состоять только из цифр.")
        return value

    def clean_display_name(self):
        value = " ".join((self.cleaned_data.get("display_name") or "").strip().split())
        if not value:
            raise forms.ValidationError("Укажите название для страницы ботов.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.platform = Bot.Platform.VK
        if commit:
            obj.save()
        return obj


class BotDetailsForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ["description", "salebot_url"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "salebot_url": forms.TextInput(attrs={"placeholder": "https://..."}),
        }


class BotStatusForm(forms.Form):
    inactive = forms.BooleanField(required=False, label="Бот неактивен")

    def __init__(self, *args, bot=None, **kwargs):
        self.bot = bot
        if self.bot is None:
            raise ValueError("Bot instance is required for BotStatusForm")
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["inactive"].initial = not self.bot.is_active

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save inactive state for invalid form")
        self.bot.is_active = not self.cleaned_data["inactive"]
        self.bot.save(update_fields=["is_active"])
        return self.bot


class BranchForm(forms.ModelForm):
    def __init__(self, *args, bot=None, **kwargs):
        self.bot = bot
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.setdefault("placeholder", "Например, Welcome")
        self.fields["code"].required = False
        self.fields["code"].widget.attrs.setdefault("placeholder", "Например, ell01")
        suggested_code = Branch.suggest_next_code(bot)
        if suggested_code:
            self.fields["code"].help_text = f"Следующий код подставлен автоматически: {suggested_code}"
            if not self.is_bound and not self.initial.get("code") and not getattr(self.instance, "pk", None):
                self.initial["code"] = suggested_code

    class Meta:
        model = Branch
        fields = ["name", "code"]

    def clean_code(self):
        value = " ".join((self.cleaned_data.get("code") or "").strip().split())
        if value:
            return value

        suggested_code = Branch.suggest_next_code(self.bot)
        if suggested_code and not getattr(self.instance, "pk", None):
            return suggested_code
        raise forms.ValidationError("Укажите код ветки.")


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "budget"]


class TagImportForm(forms.Form):
    EXPECTED_COLUMNS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    file = forms.FileField(
        label="CSV файл",
        help_text="Загрузите CSV со столбцами: " + ", ".join(EXPECTED_COLUMNS),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("Нужен файл CSV.")
        return uploaded


class BaseTaskRequestForm(forms.ModelForm):
    MAX_PHOTO_SIZE = 10 * 1024 * 1024
    ALLOWED_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    notify_me = forms.BooleanField(
        required=False,
        label="Хочу получить уведомление",
    )
    tg_username = forms.CharField(
        required=False,
        max_length=64,
        label="Username в Telegram",
    )

    class Meta:
        model = TaskRequest
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        def branch_label(obj):
            return f"{obj.bot.title} / {obj.name} ({obj.code})"
        for name, field in self.fields.items():
            if name == "branches":
                field.queryset = Branch.objects.select_related("bot").order_by(
                    "bot__platform",
                    "bot__display_name",
                    "bot__name",
                    "name",
                )
                field.label_from_instance = branch_label
                field.widget = forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"})
                if field.queryset.exists():
                    field.help_text = "Список веток: Бот / Ветка (код). Можно выбрать несколько."
                else:
                    field.help_text = "Нет доступных веток. Сначала добавьте их в разделе 'Боты'."
                continue
            if name == "deadline":
                field.input_formats = list(TASK_INPUT_FORMATS)
                field.widget = forms.DateTimeInput(
                    format="%Y-%m-%dT%H:%M",
                    attrs={"type": "datetime-local", "class": "form-control", "autocomplete": "off"},
                )
                continue
            if name == "photo":
                field.required = False
                field.help_text = "Можно выбрать файл или вставить изображение через Ctrl+V."
                field.widget = forms.ClearableFileInput(
                    attrs={
                        "class": "form-control",
                        "accept": "image/*",
                    }
                )
                continue
            if name == "comment":
                field.widget = forms.Textarea(attrs={"class": "form-control", "rows": 3, "autocomplete": "off"})
                continue
            if name == "build_token":
                field.widget = forms.PasswordInput(
                    attrs={
                        "class": "form-control",
                        "autocomplete": "new-password",
                        "data-lpignore": "true",
                    }
                )
                continue
            if name == "notify_me":
                field.widget = forms.CheckboxInput(attrs={"class": "form-check-input"})
                continue
            if name == "tg_username":
                field.widget = forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": "@username или chat_id",
                        "autocomplete": "off",
                    }
                )
                continue
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["autocomplete"] = "off"

    def _set_type(self, obj, task_type):
        obj.task_type = task_type
        return obj

    def clean_deadline(self):
        raw_value = self.data.get(self.add_prefix("deadline")) or ""
        if not raw_value.strip():
            return self.cleaned_data.get("deadline")
        try:
            return parse_task_input_datetime(raw_value)
        except ValueError:
            raise forms.ValidationError("Укажите дату и время в корректном формате.")

    def clean_photo(self):
        uploaded = self.cleaned_data.get("photo")
        if not uploaded:
            return uploaded

        extension = Path(uploaded.name or "").suffix.lower()
        if extension not in self.ALLOWED_PHOTO_EXTENSIONS:
            raise forms.ValidationError("Поддерживаются только изображения: PNG, JPG, WEBP, GIF, BMP.")

        content_type = (getattr(uploaded, "content_type", "") or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise forms.ValidationError("Загрузите изображение.")

        if uploaded.size > self.MAX_PHOTO_SIZE:
            raise forms.ValidationError("Фото должно быть не больше 10 МБ.")

        return uploaded

    def clean(self):
        cleaned = super().clean()
        notify_me = bool(cleaned.get("notify_me"))
        tg_username = (cleaned.get("tg_username") or "").strip()
        if tg_username.startswith("@"):
            tg_username = tg_username[1:]

        if notify_me and not tg_username:
            self.add_error("tg_username", "Укажите username в Telegram или chat_id.")
            return cleaned

        if tg_username:
            is_username = re.fullmatch(r"[A-Za-z0-9_]{5,32}", tg_username) is not None
            is_chat_id = re.fullmatch(r"-?\d{5,20}", tg_username) is not None
            if not is_username and not is_chat_id:
                self.add_error("tg_username", "Неверный формат. Пример: @my_user или 123456789.")

        cleaned["tg_username"] = tg_username if notify_me else ""
        return cleaned


class PatchTaskRequestForm(BaseTaskRequestForm):
    class Meta:
        model = TaskRequest
        fields = ["branches", "cjm_url", "comment", "photo", "deadline"]
        labels = {
            "branches": "Ветки",
            "cjm_url": "CJM (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branches"].required = True
        self.fields["cjm_url"].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.PATCH)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class MailingTaskRequestForm(BaseTaskRequestForm):
    class Meta:
        model = TaskRequest
        fields = ["branches", "tz_url", "comment", "photo", "deadline"]
        labels = {
            "branches": "Ветки",
            "tz_url": "ТЗ (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branches"].required = True
        self.fields["tz_url"].required = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.MAILING)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class BuildTaskRequestForm(BaseTaskRequestForm):
    bot_name = forms.CharField(
        max_length=255,
        label="Имя бота",
    )
    branch_name = forms.CharField(
        required=False,
        max_length=255,
        label="Ветка (необязательно)",
    )

    class Meta:
        model = TaskRequest
        fields = ["build_token", "cjm_url", "comment", "photo", "deadline"]
        labels = {
            "build_token": "Токен",
            "cjm_url": "CJM (ссылка)",
            "comment": "Комментарий",
            "deadline": "Дедлайн",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bot_name"].widget.attrs["placeholder"] = "@new_bot"
        self.fields["branch_name"].widget.attrs["placeholder"] = "main"
        self.fields["build_token"].required = True
        self.fields["cjm_url"].required = True

    def clean(self):
        cleaned = super().clean()
        bot_name = " ".join((cleaned.get("bot_name") or "").replace(",", " ").strip().split())
        branch_name = " ".join((cleaned.get("branch_name") or "").replace(",", " ").strip().split())

        if not bot_name:
            self.add_error("bot_name", "Укажите имя бота.")

        cleaned["bot_name"] = bot_name
        cleaned["branch_name"] = branch_name
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        self._set_type(obj, TaskRequest.Type.BUILD)
        bot_name = self.cleaned_data.get("bot_name") or ""
        branch_name = self.cleaned_data.get("branch_name") or ""
        obj.build_name = f"{bot_name} / {branch_name}" if branch_name else bot_name
        if commit:
            obj.save()
        return obj


class TaskStatusForm(forms.ModelForm):
    class Meta:
        model = TaskRequest
        fields = ["status"]
        labels = {"status": "Статус"}
        widgets = {"status": forms.Select(attrs={"class": "form-select form-select-sm"})}


class TikTokFunnelRequestForm(forms.ModelForm):
    class Meta:
        model = TikTokFunnelRequest
        fields = ["landing_endpoint", "offer", "bot_url", "comment"]
        labels = {
            "landing_endpoint": "Эндпоинт лендинга",
            "offer": "Оффер",
            "bot_url": "Ссылка на бота",
            "comment": "Комментарий",
        }
        widgets = {
            "landing_endpoint": forms.TextInput(attrs={"placeholder": "/pasha_all"}),
            "offer": forms.TextInput(attrs={"placeholder": "ell010005"}),
            "bot_url": forms.TextInput(attrs={"placeholder": "https://telegram.me/efir_tt_el_bot"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-control"
            field.widget.attrs.setdefault("class", css)
            field.widget.attrs.setdefault("autocomplete", "off")
        self.fields["landing_endpoint"].required = True
        self.fields["offer"].required = True
        self.fields["bot_url"].required = True
        self.fields["landing_endpoint"].help_text = (
            "location.pathname лендинга. Домен, query и хвостовой слэш убираются автоматически."
        )

    def clean_offer(self):
        return " ".join((self.cleaned_data.get("offer") or "").split())

    def clean_landing_endpoint(self):
        raw = self.cleaned_data.get("landing_endpoint") or ""
        endpoint = TikTokFunnelRequest.normalize_endpoint(raw)
        if not endpoint or endpoint == "/":
            raise forms.ValidationError("Укажите путь лендинга, например /pasha_all.")
        return endpoint

    def clean_bot_url(self):
        value = " ".join((self.cleaned_data.get("bot_url") or "").split())
        if not value:
            raise forms.ValidationError("Укажите ссылку на бота.")
        return value

    def clean(self):
        cleaned = super().clean()
        bot_url = cleaned.get("bot_url")
        if bot_url:
            cleaned["bot_name"] = TikTokFunnelRequest.parse_bot_name(bot_url)
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.bot_name = self.cleaned_data.get("bot_name") or TikTokFunnelRequest.parse_bot_name(obj.bot_url)
        if commit:
            obj.save()
        return obj


class LegacyExperimentForm(forms.ModelForm):
    AB_TEST_OPTIONS = [
        ("start", "Стартовый"),
        ("segmentation", "Сегментация"),
        ("number", "Номер"),
        ("subscription", "Подписка"),
        ("push", "Дожимы"),
        ("sale", "Продажа"),
        ("custom", "Свой вариант"),
    ]

    ab_test_options = forms.MultipleChoiceField(
        choices=AB_TEST_OPTIONS,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label="Варианты",
    )

    class Meta:
        model = Experiment
        fields = [
            "title",
            "wants_ab_test",
            "ab_test_options",
            "ab_test_custom_option",
            "metric_impact",
            "expected_change",
            "hypothesis",
            "traffic_volume",
            "traffic_volume_other",
            "test_duration",
            "duration_users",
            "duration_end_date",
            "comment",
            "status",
        ]
        labels = {
            "title": "Название эксперимента",
            "wants_ab_test": "Хочу АБ тест",
            "ab_test_custom_option": "Свой вариант",
            "metric_impact": "На какую метрику влияем",
            "expected_change": "Какое изменение ожидаем",
            "hypothesis": "Гипотеза",
            "traffic_volume": "Объем трафика",
            "traffic_volume_other": "Другое (объем трафика)",
            "test_duration": "Длительность теста",
            "duration_users": "До набора X пользователей",
            "duration_end_date": "Конкретная дата окончания",
            "comment": "Комментарий",
            "status": "Статус",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "ab_test_custom_option": forms.TextInput(attrs={"class": "form-control"}),
            "metric_impact": forms.TextInput(attrs={"class": "form-control"}),
            "expected_change": forms.TextInput(attrs={"class": "form-control"}),
            "hypothesis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "traffic_volume": forms.Select(attrs={"class": "form-select"}),
            "traffic_volume_other": forms.TextInput(attrs={"class": "form-control"}),
            "test_duration": forms.Select(attrs={"class": "form-select"}),
            "duration_users": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "duration_end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["wants_ab_test"].required = False

    def clean(self):
        cleaned = super().clean()
        wants_ab_test = bool(cleaned.get("wants_ab_test"))
        ab_options = cleaned.get("ab_test_options") or []

        if not wants_ab_test:
            cleaned["ab_test_options"] = []
            cleaned["ab_test_custom_option"] = ""
            cleaned["metric_impact"] = ""
            cleaned["expected_change"] = ""
            cleaned["hypothesis"] = ""
            cleaned["traffic_volume"] = ""
            cleaned["traffic_volume_other"] = ""
            cleaned["test_duration"] = ""
            cleaned["duration_users"] = None
            cleaned["duration_end_date"] = None
            return cleaned

        if not ab_options:
            self.add_error("ab_test_options", "Выберите минимум один вариант для АБ теста.")
        if "custom" in ab_options and not (cleaned.get("ab_test_custom_option") or "").strip():
            self.add_error("ab_test_custom_option", "Заполните поле 'Свой вариант'.")
        if not (cleaned.get("metric_impact") or "").strip():
            self.add_error("metric_impact", "Заполните поле метрики.")
        if not (cleaned.get("expected_change") or "").strip():
            self.add_error("expected_change", "Заполните ожидаемое изменение.")
        if not (cleaned.get("hypothesis") or "").strip():
            self.add_error("hypothesis", "Заполните гипотезу.")

        traffic_volume = cleaned.get("traffic_volume")
        if not traffic_volume:
            self.add_error("traffic_volume", "Выберите объем трафика.")
        elif traffic_volume == Experiment.TrafficVolume.OTHER and not (cleaned.get("traffic_volume_other") or "").strip():
            self.add_error("traffic_volume_other", "Укажите свой вариант объема трафика.")

        duration = cleaned.get("test_duration")
        if not duration:
            self.add_error("test_duration", "Выберите длительность теста.")
        elif duration == Experiment.TestDuration.UNTIL_USERS and not cleaned.get("duration_users"):
            self.add_error("duration_users", "Укажите количество пользователей.")
        elif duration == Experiment.TestDuration.END_DATE and not cleaned.get("duration_end_date"):
            self.add_error("duration_end_date", "Укажите дату окончания.")

        return cleaned
