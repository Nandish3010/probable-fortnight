"""Catalogue vocabulary for the synthetic Kutumb Mart tenant. Indian grocery and snacks only;
no pet products anywhere (DECISIONS §2.1). Everything here is invented."""
from __future__ import annotations

# category -> (list of (base name, pack sizes), unit cost range as fraction of price, shelf life days, is_food, weight per pack g)
CATEGORIES: dict[str, dict] = {
    "snacks": {
        "items": ["Masala Chips", "Salted Chips", "Banana Chips", "Murukku", "Mixture", "Bhujia", "Khakhra", "Peanut Chikki", "Popcorn", "Nachos", "Roasted Makhana", "Mathri", "Namak Para", "Soya Sticks", "Chakli"],
        "packs": ["100G", "200G", "500G"],
        "cost_frac": (0.72, 0.86), "shelf_life": (60, 120), "is_food": True, "price": (20, 180),
    },
    "beverages": {
        "items": ["Cola Zero", "Cola Lite", "Cola Classic", "Lemon Soda", "Mango Nectar", "Orange Juice", "Buttermilk", "Coconut Water", "Jeera Soda", "Iced Tea", "Energy Drink", "Lassi", "Rose Milk", "Cold Coffee", "Guava Juice"],
        "packs": ["250ML", "500ML", "1L"],
        "cost_frac": (0.70, 0.84), "shelf_life": (45, 180), "is_food": True, "price": (15, 140),
    },
    "staples": {
        "items": ["Toor Dal", "Moong Dal", "Chana Dal", "Basmati Rice", "Sona Masoori Rice", "Wheat Atta", "Rava", "Poha", "Quinoa", "Ragi Flour", "Besan", "Jaggery", "Sugar", "Rock Salt", "Groundnut Oil", "Sunflower Oil", "Mustard Oil", "Ghee", "Idli Rice", "Urad Dal"],
        "packs": ["500G", "1KG", "5KG"],
        "cost_frac": (0.80, 0.94), "shelf_life": (120, 365), "is_food": True, "price": (40, 900),
    },
    "sweets": {
        "items": ["Kaju Katli", "Mysore Pak", "Soan Papdi", "Gulab Jamun Tin", "Rasgulla Tin", "Besan Ladoo", "Motichoor Ladoo", "Dry Fruit Gift Box", "Peda", "Chikki Assorted", "Halwa", "Barfi"],
        "packs": ["250G", "500G", "1KG"],
        "cost_frac": (0.66, 0.80), "shelf_life": (20, 90), "is_food": True, "price": (120, 1200),
    },
    "dairy": {
        "items": ["Curd", "Paneer", "Butter", "Cheese Slices", "Toned Milk", "Full Cream Milk", "Flavoured Milk", "Cream"],
        "packs": ["200G", "400G", "500ML", "1L"],
        "cost_frac": (0.78, 0.90), "shelf_life": (7, 30), "is_food": True, "price": (25, 260),
    },
    "premium_tea": {
        "items": ["Darjeeling Tea", "Assam Gold Tea", "Nilgiri Tea", "Green Tea", "Masala Chai Blend", "Earl Grey", "White Tea"],
        "packs": ["100G", "250G"],
        "cost_frac": (0.70, 0.80), "shelf_life": (365, 540), "is_food": True, "price": (180, 900),
    },
    "bakery": {
        "items": ["Wheat Bread", "Milk Bread", "Rusk", "Khari", "Cream Bun", "Multigrain Bread", "Pav"],
        "packs": ["200G", "400G"],
        "cost_frac": (0.74, 0.86), "shelf_life": (4, 15), "is_food": True, "price": (25, 90),
    },
    "household": {
        "items": ["Dish Soap", "Floor Cleaner", "Detergent Powder", "Toilet Cleaner", "Garbage Bags", "Sponge Pack", "Phenyl", "Scrub Pad", "Air Freshener", "Laundry Liquid"],
        "packs": ["500ML", "1L", "1KG"],
        "cost_frac": (0.62, 0.78), "shelf_life": (540, 1080), "is_food": False, "price": (40, 420),
    },
    "personal_care": {
        "items": ["Shampoo", "Bath Soap", "Toothpaste", "Hair Oil", "Face Wash", "Body Lotion", "Hand Wash", "Deodorant"],
        "packs": ["100ML", "200ML", "400ML"],
        "cost_frac": (0.60, 0.76), "shelf_life": (540, 1080), "is_food": False, "price": (45, 480),
    },
}

# Category velocity scale (units per node per day at a typical dark store) and node type multipliers.
CATEGORY_VELOCITY = {
    "snacks": 6.0, "beverages": 8.0, "staples": 4.0, "sweets": 1.5, "dairy": 12.0,
    "premium_tea": 0.6, "bakery": 9.0, "household": 2.0, "personal_care": 2.5,
}
DAY_OF_WEEK_PROFILE = [0.92, 0.88, 0.90, 0.96, 1.06, 1.18, 1.10]  # Mon..Sun, mean 1.0

# Planted SKUs used by the demo script (DECISIONS §3.2 and §9). Fixed ids so fixtures can name them.
PLANTED_SKUS = {
    "SKU-MASALA-CHIPS-200G": {"name": "Masala Chips 200G", "category": "snacks", "pack_size": "200G", "pack_weight_g": 200, "unit_cost": 25.0, "list_price": 30.0, "shelf_life_days": 90, "is_food": True},
    "SKU-COLA-ZERO-500ML": {"name": "Cola Zero 500ML", "category": "beverages", "pack_size": "500ML", "pack_weight_g": 520, "unit_cost": 30.0, "list_price": 40.0, "shelf_life_days": 150, "is_food": True},
    "SKU-COLA-LITE-500ML": {"name": "Cola Lite 500ML", "category": "beverages", "pack_size": "500ML", "pack_weight_g": 520, "unit_cost": 30.0, "list_price": 40.0, "shelf_life_days": 150, "is_food": True},
    "SKU-KAJU-KATLI-250G": {"name": "Kaju Katli 250G", "category": "sweets", "pack_size": "250G", "pack_weight_g": 250, "unit_cost": 260.0, "list_price": 360.0, "shelf_life_days": 30, "is_food": True},
    "SKU-DARJEELING-TEA-100G": {"name": "Darjeeling Tea 100G", "category": "premium_tea", "pack_size": "100G", "pack_weight_g": 100, "unit_cost": 340.0, "list_price": 450.0, "shelf_life_days": 365, "is_food": True},
    "SKU-QUINOA-500G": {"name": "Quinoa 500G", "category": "staples", "pack_size": "500G", "pack_weight_g": 500, "unit_cost": 190.0, "list_price": 240.0, "shelf_life_days": 365, "is_food": True},
}

FORBIDDEN_WORDS = ("dog", "cat ", "pet", "puppy", "kitten", "litter", "kibble")
