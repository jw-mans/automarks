class GlobalWarehouseRouter:
    """Keeps the shared warehouse connection out of the ORM.

    All automarks models live in the ``default`` database. The ``global`` alias
    points at the remote warehouse (schema ``activation_data``) and is used only
    for explicit raw-SQL writes via ``connections["global"]``. This router makes
    sure Django never reads/writes ORM models there and never runs automarks'
    migrations against it (which would clash with hand-managed warehouse tables).
    """

    def db_for_read(self, model, **hints):
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == "global":
            return False
        return None
