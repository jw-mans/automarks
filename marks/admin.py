from django.contrib import admin
from .models import (
    Product,
    Bot,
    Branch,
    PlanMonthly,
    BranchPlanMonthly,
    Funnel,
    TrafficReport,
    PatchNote,
    UserProfile,
    TaskRequest,
    TikTokFunnelRequest,
    Experiment,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "bots_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    def bots_count(self, obj): return obj.bots.count()


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "name", "product", "created_at")
    list_filter = ("platform", "product")
    search_fields = ("name", "display_name", "product__name")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "bot", "product")
    list_filter = ("bot__product", "bot")
    search_fields = ("name", "code", "bot__name", "bot__product__name")

    def product(self, obj):
        return obj.bot.product
    product.short_description = "Product"


@admin.register(PlanMonthly)
class PlanMonthlyAdmin(admin.ModelAdmin):
    list_display = ("product", "month", "budget", "revenue_target", "warm_leads_target", "cold_leads_target")
    list_filter = ("product", "month")
    search_fields = ("product__name",)


@admin.register(BranchPlanMonthly)
class BranchPlanMonthlyAdmin(admin.ModelAdmin):
    list_display = ("branch", "month", "warm_leads", "cold_leads", "expected_revenue")
    list_filter = ("branch__bot__product", "branch__bot", "month")
    search_fields = ("branch__name", "branch__bot__name")


@admin.register(Funnel)
class FunnelAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "is_active", "created_at")
    list_filter = ("product", "is_active")
    search_fields = ("name", "product__name")


@admin.register(TrafficReport)
class TrafficReportAdmin(admin.ModelAdmin):
    list_display = ("product", "month", "platform", "vendor", "spend", "clicks", "leads_warm", "leads_cold")
    list_filter = ("product", "platform", "month")
    search_fields = ("vendor",)


@admin.register(PatchNote)
class PatchNoteAdmin(admin.ModelAdmin):
    list_display = ("branch", "title", "change_type", "created_by", "created_at")
    list_filter = ("change_type", "branch__bot__product")
    search_fields = ("title", "change_description")


@admin.register(TaskRequest)
class TaskRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "task_type", "status", "deadline", "created_by", "created_at", "completed_at")
    list_filter = ("task_type", "status", "deadline")
    search_fields = ("comment", "build_name", "cjm_url", "tz_url", "created_by__username")
    filter_horizontal = ("branches",)


@admin.register(TikTokFunnelRequest)
class TikTokFunnelRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "landing_endpoint", "offer", "bot_name", "status", "warehouse_synced", "created_by", "created_at")
    list_filter = ("status", "warehouse_synced")
    search_fields = ("landing_endpoint", "offer", "bot_name", "bot_url", "pixel_code")


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "start_date", "end_date", "wants_ab_test", "created_by", "created_at", "updated_at")
    list_filter = ("status", "wants_ab_test", "traffic_volume", "test_duration")
    search_fields = ("title", "metric_impact", "expected_change", "hypothesis", "comment", "result_variant_a", "result_variant_b")
