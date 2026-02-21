from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Meal(models.Model):
    CATEGORY_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('snacks', 'Snacks'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    calories = models.IntegerField()
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='breakfast',
    )
    date_added = models.DateField(default=timezone.localdate)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}) — {self.user.username}"


class InventoryItem(models.Model):
    UNIT_CHOICES = [
        ('kg',  'Kilograms (kg)'),
        ('g',   'Grams (g)'),
        ('l',   'Liters (L)'),
        ('ml',  'Milliliters (mL)'),
        ('pcs', 'Pieces (pcs)'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    name       = models.CharField(max_length=200)
    quantity   = models.DecimalField(max_digits=10, decimal_places=2)
    unit       = models.CharField(max_length=10, choices=UNIT_CHOICES, default='g')
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_added']

    def __str__(self):
        return f"{self.name} — {self.quantity} {self.unit} ({self.user.username})"


class DailyMeal(models.Model):
    CATEGORY_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch',     'Lunch'),
        ('dinner',    'Dinner'),
        ('snacks',    'Snacks'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    name       = models.CharField(max_length=200)
    calories   = models.IntegerField()
    category   = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='breakfast')
    meal_date  = models.DateField()                    # the date the user selects
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['meal_date', 'category', 'created_at']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}) on {self.meal_date} — {self.user.username}"
