"""ERP Chaos Cost Calculator — top-of-funnel, no login, no storage.

Server-side POST keeps one source of truth for the formula (testable
Python), keeps events server-side and works without JavaScript. Nothing is
persisted: the result lives only in the rendered response; ToolEvent rows
carry the anonymous numbers for funnel analytics.
"""
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from tools_core.services.analytics import track
from tools_core.utils import client_ip, rate_limit_exceeded

from .calculator import InvalidInput, compute

TOOL_SLUG = 'chaos_calculator'
CALC_LIMIT_PER_HOUR = 60  # generous: it's a calculator, not a fetcher

CURRENCIES = ['EUR', 'USD', 'GBP', 'SAR', 'AED']
CURRENCY_SYMBOLS = {'EUR': '€', 'USD': '$', 'GBP': '£', 'SAR': 'SAR', 'AED': 'AED'}

FIELD_ERRORS = {
    'employees': gettext_lazy('Enter how many employees are affected (1 to 10,000).'),
    'hours_per_employee': gettext_lazy('Enter the manual hours per employee per week (up to 80).'),
    'total_weekly_hours': gettext_lazy('Enter a valid total of weekly manual hours.'),
    'hourly_cost': gettext_lazy('Enter the average fully-loaded hourly cost (e.g. 35).'),
    'rework_hours_month': gettext_lazy('Rework hours per month must be a number (or leave it empty).'),
}
DEFAULT_FIELD_ERROR = gettext_lazy('Please check the numbers and try again.')


def landing(request):
    result = None
    error = ''
    values = {'currency': 'EUR'}

    if request.method == 'POST':
        if request.POST.get('website'):  # honeypot
            return redirect('tool_chaos_calc:landing')
        values = {key: (request.POST.get(key) or '').strip() for key in (
            'employees', 'hours_per_employee', 'total_weekly_hours',
            'hourly_cost', 'rework_hours_month', 'currency')}
        if values['currency'] not in CURRENCIES:
            values['currency'] = 'EUR'

        if rate_limit_exceeded(f'chaos-calc:{client_ip(request)}',
                               CALC_LIMIT_PER_HOUR, 3600):
            error = _('Too many calculations — please try again in a while.')
        elif not values['total_weekly_hours'] and not (
                values['employees'] and values['hours_per_employee']):
            error = _('Tell us either the team size and hours per person, '
                      'or the total weekly manual hours.')
        else:
            try:
                result = compute(
                    employees=values['employees'] or None,
                    hours_per_employee=values['hours_per_employee'] or None,
                    total_weekly_hours=values['total_weekly_hours'] or None,
                    hourly_cost=values['hourly_cost'],
                    rework_hours_month=values['rework_hours_month'] or 0,
                )
            except InvalidInput as exc:
                error = str(FIELD_ERRORS.get(str(exc), DEFAULT_FIELD_ERROR))
        if result:
            result['currency'] = values['currency']
            result['symbol'] = CURRENCY_SYMBOLS[values['currency']]
            for key in ('weekly_cost', 'monthly_cost', 'yearly_cost',
                        'rework_yearly_cost'):
                result[f'{key}_display'] = '{:,.0f}'.format(result[key])
            track(request, TOOL_SLUG, 'chaos_calculator_completed',
                  yearly_cost=result['yearly_cost'],
                  weekly_hours=result['weekly_hours'],
                  currency=values['currency'])
    else:
        track(request, TOOL_SLUG, 'chaos_calculator_page_view')

    return render(request, 'tool_chaos_calc/landing.html', {
        'result': result,
        'error': error,
        'values': values,
        'currencies': CURRENCIES,
        'meta_description': (
            'Free ERP chaos cost calculator: estimate what manual spreadsheets, '
            'double data entry and rework cost your company per year — from '
            'your own numbers, in 30 seconds. No login.'
        ),
    })


def go_rescue(request):
    track(request, TOOL_SLUG, 'chaos_calculator_rescue_clicked')
    return redirect('tool_erp_rescue:landing')


def go_xray(request):
    track(request, TOOL_SLUG, 'chaos_calculator_xray_clicked')
    return redirect('tool_studio_xray:landing')
