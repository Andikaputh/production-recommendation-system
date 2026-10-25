# Data Dictionary

## Core entities

| Entity | Key fields | Notes |
| --- | --- | --- |
| Product | `product_id`, category, description, brand, price, rating, availability, merchant, attributes | Price/rating/stock simulated |
| Merchant | `merchant_id`, name, city, rating, low-history flag | Fictitious identity |
| User profile | `user_id`, preferred categories/brands/styles/colors, sensitivity | Pseudonymous synthetic profile |
| Interaction | `event_id`, session/user/product, event type, timestamp, source | Event types: impression, click, save, add_to_list, purchase_proxy, dismiss |
| Mission | goal, required/optional categories, max budget/merchants, preferences | Hard constraints remain explicit |
| Recommendation request | request/model/strategy/status/latency/candidate count | Stores an auditable response snapshot |
| Basket solution | price, remaining budget, merchants, coverage, solver | Feasible status is revalidated |

CSV schemas and strict loaders live in `src/rasa/data/schema.py`; relational definitions live in `src/rasa/db/models.py`.
