# In memory stand in for MySQLStore so tests run offline and give the same answers every time
TEAMS = {
    1: {"id": 1, "name": "Pleasanton Hawks", "city": "Pleasanton", "contact_email": "pleasanton.hawks@s3319league.org"},
    2: {"id": 2, "name": "Santa Clara Hawks", "city": "Santa Clara", "contact_email": "santa.clara.hawks@s3319league.org"},
    3: {"id": 3, "name": "Gilroy Bears", "city": "Gilroy", "contact_email": "gilroy.bears@s3319league.org"},
}
FIXTURES = [
    {"id": 1, "fixture_code": "FX-00001", "fixture_title": "Pleasanton Hawks vs Cupertino Spartans - Matchweek 32",
     "venue": "Pleasanton Sports Complex", "tickets_available": 37, "home_team_id": 1, "created_at": "2026-10-01T17:14:36"},
    {"id": 2, "fixture_code": "FX-00002", "fixture_title": "Santa Clara Hawks vs Fremont Sharks - Matchweek 32",
     "venue": "Santa Clara Field", "tickets_available": 74, "home_team_id": 2, "created_at": "2026-10-01T17:14:36"},
    {"id": 3, "fixture_code": "FX-00003", "fixture_title": "Gilroy Bears vs Campbell Tigers - Matchweek 17",
     "venue": "Gilroy Field", "tickets_available": 111, "home_team_id": 3, "created_at": "2026-10-01T17:14:36"},
    {"id": 4, "fixture_code": "FX-00004", "fixture_title": "Gilroy Bears vs San Jose Owls - Matchweek 5",
     "venue": "Gilroy Field", "tickets_available": 300, "home_team_id": 3, "created_at": "2026-10-01T17:14:36"},
]
class FakeStore:
    """Same three methods as MySQLStore, answered from the small lists above."""
    def __init__(self, fixtures=None, teams=None):
        self.fixtures = fixtures if fixtures is not None else FIXTURES
        self.teams = teams if teams is not None else TEAMS
        self.fault = None  # same hook as MySQLStore, so retry tests can inject failures
        self.calls = 0  # how many storage calls reached this store
    def _touch(self):
        if self.fault:
            self.fault()
        self.calls += 1
    def search_fixtures(self, text: str, limit: int) -> list[dict]:
        self._touch()
        text = text.lower()
        hits = [f for f in self.fixtures if text in f["fixture_title"].lower() or text in f["venue"].lower()]
        return [{"fixture_code": f["fixture_code"], "fixture_title": f["fixture_title"], "venue": f["venue"],
                 "tickets_available": f["tickets_available"], "home_team": self.teams[f["home_team_id"]]["name"]}
                for f in hits[:limit]]
    def get_fixture(self, code: str) -> dict | None:
        self._touch()
        for f in self.fixtures:
            if f["fixture_code"] == code:
                t = self.teams[f["home_team_id"]]
                return {"id": f["id"], "fixture_code": f["fixture_code"], "fixture_title": f["fixture_title"],
                        "venue": f["venue"], "tickets_available": f["tickets_available"], "created_at": f["created_at"],
                        "team_id": t["id"], "team_name": t["name"], "team_city": t["city"], "team_email": t["contact_email"]}
        return None
    def tickets_by_city(self, top_n: int) -> list[dict]:
        self._touch()
        totals = {}
        for f in self.fixtures:
            city = self.teams[f["home_team_id"]]["city"]
            count, total = totals.get(city, (0, 0))
            totals[city] = (count + 1, total + f["tickets_available"])
        rows = [{"city": c, "fixtures": n, "total_tickets": s, "avg_tickets": round(s / n, 1)} for c, (n, s) in totals.items()]
        return sorted(rows, key=lambda r: (-r["total_tickets"], r["city"]))[:top_n]