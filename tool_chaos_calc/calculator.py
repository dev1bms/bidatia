"""Deterministic, transparent math for the ERP Chaos Cost Calculator.

The formula is deliberately simple and shown verbatim on the page:

    weekly_hours = employees x hours_per_employee   (or a total you enter)
    weekly_cost  = weekly_hours x hourly_cost
    yearly_cost  = weekly_cost x 52 + rework_hours_per_month x hourly_cost x 12

No statistics, no benchmarks, no hidden multipliers — an estimate from the
visitor's own inputs, never financial advice.
"""

WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12

# Sanity caps — generous, but they keep nonsense inputs from producing
# absurd shareable numbers under the Bidatia name.
MAX_EMPLOYEES = 10000
MAX_HOURS_PER_EMPLOYEE = 80          # per week
MAX_TOTAL_WEEKLY_HOURS = 400000      # 10k people x 40h
MAX_HOURLY_COST = 1000
MAX_REWORK_HOURS_MONTH = 20000


class InvalidInput(ValueError):
    """Raised with a machine code the view translates into a polite message."""


def compute(employees=None, hours_per_employee=None, total_weekly_hours=None,
            hourly_cost=None, rework_hours_month=0):
    """Returns the cost estimate dict. Either `total_weekly_hours` or
    (`employees` + `hours_per_employee`) must be provided."""
    hourly_cost = _positive('hourly_cost', hourly_cost, MAX_HOURLY_COST)
    rework_hours_month = _positive('rework_hours_month', rework_hours_month or 0,
                                   MAX_REWORK_HOURS_MONTH, allow_zero=True)

    if total_weekly_hours not in (None, ''):
        weekly_hours = _positive('total_weekly_hours', total_weekly_hours,
                                 MAX_TOTAL_WEEKLY_HOURS)
    else:
        employees = _positive('employees', employees, MAX_EMPLOYEES)
        hours_per_employee = _positive('hours_per_employee', hours_per_employee,
                                       MAX_HOURS_PER_EMPLOYEE)
        weekly_hours = employees * hours_per_employee

    weekly_cost = weekly_hours * hourly_cost
    yearly_cost = (weekly_cost * WEEKS_PER_YEAR
                   + rework_hours_month * hourly_cost * MONTHS_PER_YEAR)
    return {
        'weekly_hours': round(weekly_hours, 1),
        'yearly_hours': round(weekly_hours * WEEKS_PER_YEAR
                              + rework_hours_month * MONTHS_PER_YEAR, 1),
        'weekly_cost': round(weekly_cost),
        'monthly_cost': round(yearly_cost / MONTHS_PER_YEAR),
        'yearly_cost': round(yearly_cost),
        'rework_yearly_cost': round(rework_hours_month * hourly_cost
                                    * MONTHS_PER_YEAR),
    }


def _positive(name, value, maximum, allow_zero=False):
    try:
        number = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise InvalidInput(name)
    if number != number or number in (float('inf'), float('-inf')):
        raise InvalidInput(name)
    if number < 0 or (number == 0 and not allow_zero) or number > maximum:
        raise InvalidInput(name)
    return number
