from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import (ClientProfile, DeliveryPoint, DeliverySlot, HarvestItem,
                     HarvestWeek, Order, OrderItem, Producer, Product)


class ProducerInline(admin.StackedInline):
    model = Producer
    can_delete = False
    show_change_link = True


class ClientInline(admin.StackedInline):
    model = ClientProfile
    can_delete = False
    show_change_link = True


class PortalUserAdmin(UserAdmin):
    inlines = [ProducerInline, ClientInline]


admin.site.unregister(User)
admin.site.register(User, PortalUserAdmin)


class HarvestItemInline(admin.TabularInline):
    model = HarvestItem
    extra = 0


@admin.register(Producer)
class ProducerAdmin(admin.ModelAdmin):
    list_display = ("farm_name", "city", "department", "certification", "is_visible")
    list_filter = ("certification", "is_visible", "department")
    search_fields = ("farm_name", "city", "siret")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "producer", "category", "unit", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "producer__farm_name")


@admin.register(HarvestWeek)
class HarvestWeekAdmin(admin.ModelAdmin):
    list_display = ("producer", "week_start", "is_published")
    list_filter = ("is_published",)
    inlines = [HarvestItemInline]


@admin.register(DeliveryPoint)
class DeliveryPointAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "zip_code", "producer")
    search_fields = ("name", "city")


@admin.register(DeliverySlot)
class DeliverySlotAdmin(admin.ModelAdmin):
    list_display = ("producer", "day_of_week", "start_time", "end_time",
                    "frequency", "capacity", "delivery_point")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "producer", "client", "delivery_date", "status", "total")
    list_filter = ("status", "delivery_date")
    inlines = [OrderItemInline]
