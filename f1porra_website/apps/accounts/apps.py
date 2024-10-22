from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'f1porra_website.apps.accounts'

    def ready(self):
        import f1porra_website.apps.accounts.signals
