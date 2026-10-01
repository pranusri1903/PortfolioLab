"""Load sample market data and a demo portfolio: python -m app.seed [--owner-id ID]"""

import argparse

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Portfolio
from app.repositories import data as repo
from app.services.demo import load_demo_transactions, seed_market_data

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-id", default="demo_user")
    ap.add_argument("--market-only", action="store_true", help="only load assets and prices")
    args = ap.parse_args()
    owner = args.owner_id
    with Session(get_engine()) as s:
        seed_market_data(s)
        if args.market_only:
            print("Seeded sample market data.")
        elif not repo.list_portfolios(s, owner):
            p = Portfolio(owner_id=owner, name="Demo Portfolio", is_demo=True)
            s.add(p)
            s.flush()
            load_demo_transactions(s, p)
        print(f"Seeded sample data; demo portfolio for owner '{owner}'.")
