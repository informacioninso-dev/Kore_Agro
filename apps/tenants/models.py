from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Client(TenantMixin):
    name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=200, blank=True)
    ruc = models.CharField(max_length=13, blank=True)
    province = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    paid_until = models.DateField(null=True, blank=True)
    on_trial = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self) -> str:
        return self.name


class Domain(DomainMixin):
    pass

