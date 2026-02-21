import requests as http_requests
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Meal

# ── Edamam credentials ────────────────────────────────────────────────────────
EDAMAM_APP_ID  = '6d6bf9be'
EDAMAM_APP_KEY = '852c746609088255d77a762c3cd29a7a'
EDAMAM_URL     = 'https://api.edamam.com/api/nutrition-data'


def _lookup_cached_calories(food_name: str) -> int | None:
    """
    Check SQLite for any previously saved meal whose name matches
    (case-insensitive). Returns calories if found, else None.
    Checks the current user's meals first (via all Meals), since we call
    this before knowing the user — caller can pass user-scoped queryset too.
    """
    match = (
        Meal.objects
        .filter(name__iexact=food_name)
        .values_list('calories', flat=True)
        .first()
    )
    return match


def _call_edamam(food_name: str):
    """
    Hit the Edamam Nutrition Analysis API.
    Returns (calories: int, error_msg: str | None).
    """
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




# ── Welcome / Landing Page (public) ──────────────────────────────────────────

def welcome(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/index.html')


# ── Meal Dashboard (protected) ────────────────────────────────────────────────

@login_required(login_url='login')
def dashboard(request):
    if request.method == 'POST':
        meal_input     = request.POST.get('meal_name', '').strip()
        manual_cal_str = request.POST.get('calories', '').strip()

        if not meal_input:
            messages.error(request, "Please enter a meal name.")
            return redirect('dashboard')

        # ══ TIER 1 — Manual entry (no API call at all) ═══════════════════════
        if manual_cal_str:
            try:
                manual_calories = int(float(manual_cal_str))
                Meal.objects.create(user=request.user, name=meal_input, calories=manual_calories)
                messages.success(request, f"✅ '{meal_input}' logged manually — {manual_calories} kcal!")
            except ValueError:
                messages.error(request, "Please enter a valid number for calories.")
            return redirect('dashboard')

        # ══ TIER 2 — Local SQLite cache check (saves an API call) ════════════
        # 2a. Check this user's own meal history first
        user_cached = (
            Meal.objects
            .filter(user=request.user, name__iexact=meal_input)
            .values_list('calories', flat=True)
            .first()
        )
        if user_cached is not None:
            Meal.objects.create(user=request.user, name=meal_input, calories=user_cached)
            messages.success(
                request,
                f"✅ '{meal_input}' logged — {user_cached} kcal (from your history, no API call used!)"
            )
            return redirect('dashboard')

        # 2b. Check ALL users' meals (global cache)
        global_cached = _lookup_cached_calories(meal_input)
        if global_cached is not None:
            Meal.objects.create(user=request.user, name=meal_input, calories=global_cached)
            messages.success(
                request,
                f"✅ '{meal_input}' logged — {global_cached} kcal (from cached data, no API call used!)"
            )
            return redirect('dashboard')

        # ══ TIER 3 — Fresh food: call Edamam API ═════════════════════════════
        calories, err = _call_edamam(meal_input)

        if err is None:
            # ✅ API success
            Meal.objects.create(user=request.user, name=meal_input, calories=calories)
            messages.success(request, f"✅ '{meal_input}' logged — {calories} kcal (via Edamam API)")

        elif err == '429':
            # API rate-limited → try a fuzzy fallback from the DB
            fuzzy = (
                Meal.objects
                .filter(name__icontains=meal_input.split()[0])   # match first word
                .values_list('calories', flat=True)
                .first()
            )
            if fuzzy:
                Meal.objects.create(user=request.user, name=meal_input, calories=fuzzy)
                messages.warning(
                    request,
                    f"⚠ API limit reached. Using estimated value: {fuzzy} kcal for '{meal_input}'."
                )
            else:
                messages.error(
                    request,
                    "API is resting. Please wait 60 seconds or try a food you've entered before!"
                )

        elif err == 'not_found':
            messages.error(
                request,
                "❓ Food not recognized. Try '300g chicken' format, or enter calories manually."
            )

        elif err == 'timeout':
            messages.error(
                request,
                "⏱ API timed out. Enter calories manually or try again shortly."
            )

        else:
            messages.error(request, "⚠ API unavailable. Please enter calories manually.")

        return redirect('dashboard')

    # ── GET ───────────────────────────────────────────────────────────────────
    meals          = Meal.objects.filter(user=request.user).order_by('-id')
    total_calories = sum(meal.calories for meal in meals)
    context = {
        'meals':          meals,
        'total_calories': total_calories,
    }
    return render(request, 'tracker/dashboard.html', context)





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


# ── Delete Meal ───────────────────────────────────────────────────────────────

@login_required(login_url='login')
def delete_meal(request, meal_id):
    meal = Meal.objects.get(id=meal_id, user=request.user)
    meal.delete()
    return redirect('dashboard')
