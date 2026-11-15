"""Card vocabulary and choice priorities, independent of vision."""

from difflib import get_close_matches
import re


NAMES = (
    'Damage Mastery', 'Signature Mastery', 'Overcharge', 'Speed Mastery',
    'Rapid Fire', 'Overclocked Turrets', 'Turret Mastery', 'Trap Mastery',
    'Gate Mastery', 'RC Mastery', 'Supply Mastery', 'Field Repairs',
    'Quick Hands', 'Spare Quinque', 'Big Bang', 'Incendiary Mines',
    'Thunder Lock', 'Napalm Core', 'Splinter Bolts', 'Chain Bolts',
    'Cluster Grenade', 'Twin Strike', 'Twin Scythes', 'Tar Road', 'Shock Net',
    'Kakuja Core', "Takizawa's Grin", 'Dragon Scale', "Big Madam's Pearls",
    "Gourmet's Recipe", 'Black Rabbit Wing', "Rabbit's Mask", "Tatara's Ember",
)


def clean(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


CANONICAL = {clean(name): name for name in NAMES}


def canonical(text):
    key = clean(text)
    found = get_close_matches(key, CANONICAL, n=1, cutoff=0.82)
    return CANONICAL[found[0]] if found else text.strip()


def priority(name):
    order = (
        'Twin Scythes', 'Damage Mastery', 'Signature Mastery', 'Overcharge',
        'Black Rabbit Wing', 'Kakuja Core',
        'Speed Mastery', 'Rapid Fire', "Rabbit's Mask",
        'Overclocked Turrets', 'Turret Mastery', 'Trap Mastery', "Tatara's Ember",
    )
    normalized = clean(name)
    return next((i for i, value in enumerate(order) if clean(value) == normalized), 100)


def choose(names):
    return min(range(len(names)), key=lambda i: (priority(names[i]), i))
