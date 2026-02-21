import re
import json
import requests as http_requests
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from .models import Meal, InventoryItem, DailyMeal
from datetime import timedelta

# ── Edamam credentials ────────────────────────────────────────────────────────
EDAMAM_APP_ID  = '6d6bf9be'
EDAMAM_APP_KEY = '852c746609088255d77a762c3cd29a7a'
EDAMAM_URL     = 'https://api.edamam.com/api/nutrition-data'


def _lookup_cached_calories(food_name: str) -> int | None:
    match = (
        Meal.objects
        .filter(name__iexact=food_name)
        .values_list('calories', flat=True)
        .first()
    )
    return match


def _call_edamam(food_name: str):
    try:
        resp = http_requests.get(
            EDAMAM_URL,
            params={
                'app_id':  EDAMAM_APP_ID,
                'app_key': EDAMAM_APP_KEY,
                'ingr':    food_name,
            },
            timeout=10,
        )
        if resp.status_code == 429:
            return None, '429'
        if resp.status_code in (404, 422):
            return None, 'not_found'
        if resp.status_code == 200:
            data   = resp.json()
            parsed = data.get('ingredients', [{}])[0].get('parsed', [])
            if not parsed:
                return None, 'not_found'
            kcal = round(parsed[0]['nutrients']['ENERC_KCAL']['quantity'])
            return kcal, None
        return None, 'error'
    except http_requests.exceptions.Timeout:
        return None, 'timeout'
    except http_requests.exceptions.RequestException:
        return None, 'error'


def _get_health_suggestion(total_calories: int) -> dict:
    if total_calories == 0:
        return {
            'text': "You haven't logged any meals yet. Start adding food to get personalized insights!",
            'type': 'info',
            'emoji': '📝',
        }
    elif total_calories < 1200:
        return {
            'text': f"Only {total_calories} kcal today — that's quite low! Make sure you're eating enough to fuel your body.",
            'type': 'danger',
            'emoji': '⚠️',
        }
    elif total_calories < 1500:
        return {
            'text': f"{total_calories} kcal so far — a bit under your daily target. Try adding a healthy snack like nuts or fruit!",
            'type': 'warning',
            'emoji': '🍎',
        }
    elif total_calories <= 2200:
        return {
            'text': f"Perfect balance! {total_calories} kcal — you're right on track. Keep it up! 💪",
            'type': 'success',
            'emoji': '✅',
        }
    elif total_calories <= 2800:
        return {
            'text': f"{total_calories} kcal — you've gone a bit over. Consider a light walk or lighter next meal.",
            'type': 'warning',
            'emoji': '🚶',
        }
    else:
        return {
            'text': f"{total_calories} kcal — that's significantly over the recommended intake. Try balancing tomorrow!",
            'type': 'danger',
            'emoji': '🔴',
        }


# ── Welcome ───────────────────────────────────────────────────────────────────

def welcome(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/index.html')


# ── Helper: resolve calories (cache → API) ────────────────────────────────────

def _resolve_calories(request, meal_input, manual_cal_str, category):
    """
    Shared logic for resolving calories.
    Returns (calories: int | None, redirect_to: str).
    If calories is None, an error message was already set.
    """
    # Manual entry
    if manual_cal_str:
        try:
            cal = int(float(manual_cal_str))
            return cal, None
        except ValueError:
            messages.error(request, "Please enter a valid number for calories.")
            return None, 'error'

    # User cache
    user_cached = (
        Meal.objects
        .filter(user=request.user, name__iexact=meal_input)
        .values_list('calories', flat=True)
        .first()
    )
    if user_cached is not None:
        messages.success(request, f"✅ '{meal_input}' — {user_cached} kcal (from your history)")
        return user_cached, None

    # Global cache
    global_cached = _lookup_cached_calories(meal_input)
    if global_cached is not None:
        messages.success(request, f"✅ '{meal_input}' — {global_cached} kcal (from cache)")
        return global_cached, None

    # Edamam API
    calories, err = _call_edamam(meal_input)

    if err is None:
        messages.success(request, f"✅ '{meal_input}' — {calories} kcal (via Edamam API)")
        return calories, None
    elif err == '429':
        fuzzy = (
            Meal.objects
            .filter(name__icontains=meal_input.split()[0])
            .values_list('calories', flat=True)
            .first()
        )
        if fuzzy:
            messages.warning(request, f"⚠ API limit reached. Estimated: {fuzzy} kcal for '{meal_input}'.")
            return fuzzy, None
        else:
            messages.error(request, "API is resting. Wait 60s or enter calories manually!")
            return None, 'error'
    elif err == 'not_found':
        messages.error(request, "❓ Food not recognized. Try '300g chicken' format, or enter calories manually.")
        return None, 'error'
    elif err == 'timeout':
        messages.error(request, "⏱ API timed out. Enter calories manually or try again.")
        return None, 'error'
    else:
        messages.error(request, "⚠ API unavailable. Please enter calories manually.")
        return None, 'error'


# ── Dashboard (simple meal log) ───────────────────────────────────────────────

@login_required(login_url='login')
def dashboard(request):
    if request.method == 'POST':
        meal_input     = request.POST.get('meal_name', '').strip()
        manual_cal_str = request.POST.get('calories', '').strip()

        if not meal_input:
            messages.error(request, "Please enter a meal name.")
            return redirect('dashboard')

        cal, err = _resolve_calories(request, meal_input, manual_cal_str, 'breakfast')
        if cal is not None:
            Meal.objects.create(
                user=request.user,
                name=meal_input,
                calories=cal,
                category='breakfast',
            )
        return redirect('dashboard')

    meals          = Meal.objects.filter(user=request.user).order_by('-id')
    total_calories = sum(m.calories for m in meals)
    context = {
        'meals':          meals,
        'total_calories': total_calories,
    }
    return render(request, 'tracker/dashboard.html', context)


# ── Track Meals ───────────────────────────────────────────────────────────────

def _draft_key(user_id, date_str):
    """Session key for a user's draft meals for a given date."""
    return f'draft_meals_{user_id}_{date_str}'


@login_required(login_url='login')
def track_meals(request):
    today = timezone.localdate()
    from datetime import date as dt_date

    # Resolve date
    if request.method == 'POST':
        date_str = request.POST.get('meal_date', str(today))
    else:
        date_str = request.GET.get('date', str(today))

    try:
        selected_date = dt_date.fromisoformat(date_str)
    except (ValueError, TypeError):
        selected_date = today

    date_str = str(selected_date)
    skey = _draft_key(request.user.id, date_str)

    # ── POST actions ──────────────────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action', 'add')

        if action == 'add':
            meal_input     = request.POST.get('meal_name', '').strip()
            manual_cal_str = request.POST.get('calories', '').strip()
            category       = request.POST.get('category', 'breakfast')

            valid = [c[0] for c in DailyMeal.CATEGORY_CHOICES]
            if category not in valid:
                category = 'breakfast'

            if not meal_input:
                messages.error(request, 'Please enter a food item.')
                return redirect(f'/track-meals/?date={date_str}')

            cal, err = _resolve_calories(request, meal_input, manual_cal_str, category)
            if cal is not None:
                draft = request.session.get(skey, [])
                draft.append({
                    'name':     meal_input,
                    'calories': cal,
                    'category': category,
                })
                request.session[skey] = draft
                request.session.modified = True
                messages.success(request, f'"{meal_input}" added — click Save Day to store it.')

        elif action == 'remove_draft':
            idx = int(request.POST.get('draft_index', -1))
            draft = request.session.get(skey, [])
            if 0 <= idx < len(draft):
                removed = draft.pop(idx)
                request.session[skey] = draft
                request.session.modified = True
                messages.success(request, f'"{removed["name"]}" removed from draft.')

        elif action == 'save_day':
            draft = request.session.get(skey, [])
            if not draft:
                messages.error(request, 'Nothing to save — add some food first!')
            else:
                inventory_warnings = []
                items_updated = 0

                for item in draft:
                    # ── Persist the meal ───────────────────────────────────────
                    DailyMeal.objects.create(
                        user=request.user,
                        name=item['name'],
                        calories=item['calories'],
                        category=item['category'],
                        meal_date=selected_date,
                    )

                    # ── Smart Inventory Bridge ─────────────────────────────────
                    # Parse quantity and food name from the draft item name.
                    # Expected format examples: "300g chicken", "2 eggs", "500 ml milk"
                    # Strategy: split the name, try to extract a leading numeric token.
                    raw_name = item['name'].strip()
                    # Match an optional leading number (int or float) possibly
                    # attached to letters (e.g. "300g"), followed by the food name.
                    m = re.match(
                        r'^(\d+(?:\.\d+)?)\s*(?:g|kg|ml|l|pcs|piece|pieces|x)?\s+(.+)$',
                        raw_name, re.IGNORECASE
                    )
                    if m:
                        meal_qty   = float(m.group(1))
                        food_name  = m.group(2).strip()
                    else:
                        # No leading quantity found — treat the whole string as
                        # the food name and deduct 1 unit.
                        meal_qty  = 1
                        food_name = raw_name

                    inv_item = InventoryItem.objects.filter(
                        name__iexact=food_name,
                        user=request.user,
                    ).first()

                    if inv_item:
                        new_qty = float(inv_item.quantity) - meal_qty
                        if new_qty <= 0:
                            inv_item.quantity = 0
                            inventory_warnings.append(inv_item.name)
                        else:
                            inv_item.quantity = round(new_qty, 2)
                        inv_item.save()
                        items_updated += 1

                # Clear the draft session
                del request.session[skey]
                request.session.modified = True

                # ── Build feedback messages ────────────────────────────────────
                messages.success(
                    request,
                    f'✅ {len(draft)} meal(s) saved for '
                    f'{selected_date.strftime("%d %b %Y")} and Inventory updated!'
                )
                for food in inventory_warnings:
                    messages.warning(
                        request,
                        f'⚠️ Warning: You are out of {food}!'
                    )

        return redirect(f'/track-meals/?date={date_str}')

    # ── GET: build per-category data ──────────────────────────────────────────
    draft_items = request.session.get(skey, [])

    # Already-saved meals for this date (from previous Save Day calls)
    saved_meals = DailyMeal.objects.filter(user=request.user, meal_date=selected_date)

    cat_emojis = {'breakfast': '🌅', 'lunch': '☀️', 'dinner': '🌙', 'snacks': '🍿'}
    cat_labels = dict(DailyMeal.CATEGORY_CHOICES)

    # Build sections combining saved + draft
    category_sections = {}
    for key, label in DailyMeal.CATEGORY_CHOICES:
        saved_cat   = list(saved_meals.filter(category=key))
        draft_cat   = [
            {'name': d['name'], 'calories': d['calories'],
             'draft_index': i, 'is_draft': True}
            for i, d in enumerate(draft_items) if d['category'] == key
        ]
        saved_total = sum(m.calories for m in saved_cat)
        draft_total = sum(d['calories'] for d in draft_cat)
        category_sections[key] = {
            'label':       label,
            'emoji':       cat_emojis.get(key, '🍽️'),
            'saved_meals': saved_cat,
            'draft_meals': draft_cat,
            'total':       saved_total + draft_total,
            'saved_total': saved_total,
            'draft_total': draft_total,
        }

    total_calories = sum(s['total'] for s in category_sections.values())
    suggestion     = _get_health_suggestion(total_calories)
    max_cal        = max((s['total'] for s in category_sections.values()), default=1) or 1
    draft_count    = len(draft_items)

    context = {
        'category_sections': category_sections,
        'total_calories':    total_calories,
        'suggestion':        suggestion,
        'today':             today,
        'selected_date':     selected_date,
        'prev_day':          selected_date - timedelta(days=1),
        'next_day':          selected_date + timedelta(days=1),
        'max_cal':           max_cal,
        'draft_count':       draft_count,
        'date_str':          date_str,
    }
    return render(request, 'tracker/track_meals.html', context)


# ── Delete saved DailyMeal entry ──────────────────────────────────────────────

@login_required(login_url='login')
def delete_tracked_meal(request, meal_id):
    meal = DailyMeal.objects.get(id=meal_id, user=request.user)
    date = meal.meal_date
    meal.delete()

    return redirect(f"/track-meals/?date={date}")


# ── Sign Up ───────────────────────────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'tracker/signup.html', {'form': form})


# ── Login ─────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'tracker/login.html', {'form': form})


# ── Logout ────────────────────────────────────────────────────────────────────

def logout_view(request):
    logout(request)
    return redirect('login')


# ── Delete Meal (from dashboard) ─────────────────────────────────────────────

@login_required(login_url='login')
def delete_meal(request, meal_id):
    meal = Meal.objects.get(id=meal_id, user=request.user)
    meal.delete()
    return redirect('dashboard')


# ── Inventory ─────────────────────────────────────────────────────────────────

@login_required(login_url='login')
def inventory(request):
    if request.method == 'POST':
        name     = request.POST.get('name', '').strip()
        quantity = request.POST.get('quantity', '').strip()
        unit     = request.POST.get('unit', 'g')

        valid_units = [u[0] for u in InventoryItem.UNIT_CHOICES]
        if unit not in valid_units:
            unit = 'g'

        if not name:
            messages.error(request, 'Please enter an item name.')
            return redirect('inventory')
        try:
            qty = float(quantity)
            if qty < 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please enter a valid quantity.')
            return redirect('inventory')

        InventoryItem.objects.create(
            user=request.user,
            name=name,
            quantity=qty,
            unit=unit,
        )
        messages.success(request, f"'{name}' added to inventory!")
        return redirect('inventory')

    items = InventoryItem.objects.filter(user=request.user)
    context = {
        'items':       items,
        'unit_choices': InventoryItem.UNIT_CHOICES,
    }
    return render(request, 'tracker/inventory.html', context)


@login_required(login_url='login')
def delete_inventory_item(request, item_id):
    item = InventoryItem.objects.get(id=item_id, user=request.user)
    item.delete()
    return redirect('inventory')


@login_required(login_url='login')
def update_inventory_item(request, item_id):
    if request.method == 'POST':
        item     = InventoryItem.objects.get(id=item_id, user=request.user)
        quantity = request.POST.get('quantity', '').strip()
        unit     = request.POST.get('unit', item.unit)

        valid_units = [u[0] for u in InventoryItem.UNIT_CHOICES]
        if unit not in valid_units:
            unit = item.unit

        try:
            qty = float(quantity)
            if qty < 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please enter a valid quantity.')
            return redirect('inventory')

        item.quantity = qty
        item.unit     = unit
        item.save()
        messages.success(request, f"'{item.name}' updated to {qty} {unit}.")
    return redirect('inventory')
