# HW4 Part 3: seed 200 teams and 5,000 fixtures with SEED 3319
import random
from datetime import datetime
from sqlalchemy import insert, text
from .database import engine
from .models import Fixture, Team
SEED = 3319  # SID4
N_TEAMS = 200
N_FIXTURES = 5000
CITIES = ["San Jose", "Oakland", "Fremont", "Palo Alto", "Santa Clara", "Sunnyvale", "Milpitas", "Hayward",
          "Berkeley", "Cupertino", "Campbell", "Mountain View", "Redwood City", "San Mateo", "Daly City",
          "Walnut Creek", "Pleasanton", "Livermore", "Gilroy", "Morgan Hill"]  # 20 cities
MASCOTS = ["Spartans", "Bulldogs", "Lions", "Tigers", "Hawks", "Eagles", "Wolves", "Bears", "Falcons", "Sharks"]  # 10 names
VENUE_TYPES = ["Stadium", "Park", "Arena", "Field", "Sports Complex"]
def build_rows():
    rng = random.Random(SEED)  # seeded generator
    names = [(f"{city} {mascot}", city) for city in CITIES for mascot in MASCOTS]  # 20 x 10 = 200 teams
    rng.shuffle(names)
    teams = [{"id": i + 1, "name": n, "city": c} for i, (n, c) in enumerate(names)]
    fixtures = []
    for i in range(N_FIXTURES):
        home = teams[i % N_TEAMS]  # every team hosts 25 fixtures
        away = rng.choice([t for t in teams if t["id"] != home["id"]])
        week = rng.randint(1, 38)
        venue = f"{home['city']} {rng.choice(VENUE_TYPES)}"  # 100 possible venues
        fixtures.append({"fixture_title": f"{home['name']} vs {away['name']} - Matchweek {week}",
                         "venue": venue, "home_team_id": home["id"]})  # link to the related team
    return teams, fixtures
def main():
    teams, fixtures = build_rows()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))  # allow clearing tables linked by a foreign key
        conn.execute(text("TRUNCATE TABLE fixtures"))  # empty and reset AUTO_INCREMENT to 1
        conn.execute(text("TRUNCATE TABLE teams"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.execute(insert(Team), teams)  # 200 related rows
        conn.execute(insert(Fixture), fixtures)  # 5,000 primary rows
    print(f"[{datetime.now().isoformat(timespec='seconds')}] seed={SEED} teams={len(teams)} fixtures={len(fixtures)}")
if __name__ == "__main__":
    main()