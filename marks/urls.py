from django.urls import path
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import never_cache
from marks import views, views_products


def root_redirect(request):
    """Главная страница — редирект в зависимости от авторизации."""
    if request.user.is_authenticated:
        return redirect(views.get_role_home_view_name(request.user))
    return redirect("/accounts/login/")


@never_cache
def safe_login_view(request, *args, **kwargs):
    """Login без redirect_authenticated_user и без ошибок 500."""
    if request.user.is_authenticated:
        return redirect(views.get_role_home_view_name(request.user))
    view = views.RoleAwareLoginView.as_view()
    return view(request, *args, **kwargs)


urlpatterns = [

    path("", root_redirect, name="home"),
    path("accounts/login/", safe_login_view, name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export/excel/", views.export_excel, name="export_excel"),
    path("dashboard/export/pdf/", views.export_pdf, name="export_pdf"),
    path("tasks/", views.tasks_board, name="tasks_board"),
    path("tasks/export/completed/", views.export_completed_tasks, name="export_completed_tasks"),
    path("tasks/create/patch/", views.create_patch_task, name="create_patch_task"),
    path("tasks/create/mailing/", views.create_mailing_task, name="create_mailing_task"),
    path("tasks/create/build/", views.create_build_task, name="create_build_task"),
    path("tasks/<int:task_id>/status/", views.update_task_status, name="update_task_status"),
    path("tiktok-funnels/", views.tiktok_funnels, name="tiktok_funnels"),
    path("tiktok-funnels/create/", views.create_tiktok_funnel, name="create_tiktok_funnel"),
    path("tiktok-funnels/<int:funnel_id>/sync/", views.retry_tiktok_funnel_sync, name="retry_tiktok_funnel_sync"),
    path("tiktok-funnels/<int:funnel_id>/activate/", views.activate_tiktok_funnel, name="activate_tiktok_funnel"),
    path("experiments/", views.experiments_board, name="experiments_board"),
    path("experiments/<int:experiment_id>/status/", views.update_experiment_status, name="update_experiment_status"),
    path("bots/", views.bots_list, name="bots_list"),
    path("bot/<int:bot_id>/", views.branches_list, name="branches_list"),
    path("branch/<int:branch_id>/", views.tags_list, name="tags_list"),
    path("tag/<int:tag_id>/edit/", views.edit_tag, name="edit_tag"),
    path("tag/<int:tag_id>/duplicate/", views.duplicate_tag, name="duplicate_tag"),
    path("tag/<int:tag_id>/delete/", views.delete_tag, name="delete_tag"),
    path("branch/<int:branch_id>/copy/", views.copy_tags, name="copy_tags"),
    path("branch/<int:branch_id>/paste/", views.paste_tags, name="paste_tags"),
    path("branch/<int:branch_id>/import/", views.import_tags_csv, name="import_tags_csv"),
    path("branch/<int:branch_id>/duplicate_all/", views.duplicate_all_tags, name="duplicate_all_tags"),
    path("branch/<int:branch_id>/undo/", views.undo_tags_action, name="undo_tags_action"),
    path("api/bot/<str:bot_name>/", views.bot_api, name="bot_api"),
    path("products/", views_products.products_list, name="products_list"),
    path("products/<int:product_id>/", views_products.product_detail, name="product_detail"),
    path("plans/new/", views_products.plan_create, name="plan_create"),
    path("funnels/new/", views_products.funnel_master_create, name="funnel_create"),
    path("traffic/new/", views_products.traffic_report_create, name="traffic_create"),
    path("patch/new/", views_products.patchnote_create, name="patch_create"),
    path("product/<int:product_id>/reports/", views.product_reports, name="product_reports"),
    path("update_field/", views.update_field, name="update_field"),
    path("telegram/webhook/<str:webhook_key>/", views.telegram_webhook, name="telegram_webhook"),
]
