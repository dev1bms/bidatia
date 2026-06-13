"""Shared Tailwind class strings for form widgets.

Centralized here so the booking and contact forms (and any future forms) stay
visually consistent without duplicating long class strings.
"""

TEXT_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-slate-900 '
    'placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-100 outline-none transition'
)
TEXTAREA_CLASSES = TEXT_INPUT_CLASSES + ' min-h-[120px] resize-y'
SELECT_CLASSES = TEXT_INPUT_CLASSES + ' appearance-none'
CHECKBOX_CLASSES = 'h-5 w-5 rounded border-slate-300 text-sky-600 focus:ring-sky-500 mt-0.5'
