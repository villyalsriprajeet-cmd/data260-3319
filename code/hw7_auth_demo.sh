#!/usr/bin/env bash
# HW7 Part 1 demo: JWT login, /auth/me, role checks on /fixtures (run from repo root, API on 8619)
# usage: bash code/hw7_auth_demo.sh [login|me|invalid|create|delete|list|all]
set -a; source code/api/.env; set +a  # passwords come from .env, never typed here
BASE="http://localhost:8619"
LOG="reports/hw07/RUN_LOG.txt"
mkdir -p reports/hw07
req() {  # req "<label shown on screen>" curl-args... : prints the request, then body and HTTP status
  echo "\$ $1"; shift
  curl -s -w '\nHTTP %{http_code}\n' "$@"; echo
}
token() {
  curl -s -X POST "$BASE/auth/login" -d "username=$1" --data-urlencode "password=$2" |
    python3 -c 'import sys, json; print(json.load(sys.stdin).get("access_token", ""))'
}
new_fixture() {  # unique code each run so the demo can be repeated
  echo "{\"fixture_title\": \"Gilroy Bears vs San Jose Hawks - Matchweek 9\", \"fixture_code\": \"FX-9$((RANDOM % 9000 + 1000))\", \"venue\": \"Gilroy Field\", \"tickets_available\": 250, \"home_team_id\": 1}"
}
part_login() {
  echo "== 1. Login: valid credentials -> JWT, invalid -> 401 =="
  req "curl -X POST $BASE/auth/login -d username=s3319_writer -d password=\$WRITER_PASSWORD" \
    -X POST "$BASE/auth/login" -d "username=s3319_writer" --data-urlencode "password=$WRITER_PASSWORD"
  req "curl -X POST $BASE/auth/login -d username=s3319_writer -d password=wrong-password" \
    -X POST "$BASE/auth/login" -d "username=s3319_writer" -d "password=wrong-password"
}
part_me() {
  echo "== 2. GET /auth/me without a token -> 401, with a valid token -> 200 =="
  req "curl $BASE/auth/me" "$BASE/auth/me"
  R=$(token s3319_reader "$READER_PASSWORD")
  req "curl $BASE/auth/me -H 'Authorization: Bearer ${R:0:25}...'" "$BASE/auth/me" -H "Authorization: Bearer $R"
}
part_invalid() {
  echo "== 3. GET /auth/me with an invalid token and an expired token -> 401 =="
  req "curl $BASE/auth/me -H 'Authorization: Bearer not.a.real-token'" "$BASE/auth/me" -H "Authorization: Bearer not.a.real-token"
  EXP=$(python3 -m code.api.expired_token s3319_reader)
  req "curl $BASE/auth/me -H 'Authorization: Bearer ${EXP:0:25}...'  (signed, exp = 1 minute ago)" "$BASE/auth/me" -H "Authorization: Bearer $EXP"
}
part_create() {
  echo "== 4. POST /fixtures as reader -> 403, as writer -> 201 =="
  R=$(token s3319_reader "$READER_PASSWORD"); W=$(token s3319_writer "$WRITER_PASSWORD")
  B=$(new_fixture)
  req "curl -X POST $BASE/fixtures -H 'Authorization: Bearer <reader token>' -d '$B'" \
    -X POST "$BASE/fixtures" -H "Authorization: Bearer $R" -H "Content-Type: application/json" -d "$B"
  req "curl -X POST $BASE/fixtures -H 'Authorization: Bearer <writer token>' -d '$B'" \
    -X POST "$BASE/fixtures" -H "Authorization: Bearer $W" -H "Content-Type: application/json" -d "$B"
}
part_delete() {
  echo "== 5. DELETE /fixtures/{id} as writer -> 403, as moderator -> 200 =="
  W=$(token s3319_writer "$WRITER_PASSWORD"); M=$(token s3319_moderator "$MODERATOR_PASSWORD")
  ID=$(curl -s -X POST "$BASE/fixtures" -H "Authorization: Bearer $W" -H "Content-Type: application/json" -d "$(new_fixture)" |
    python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
  echo "(writer created fixture id $ID to delete)"
  req "curl -X DELETE $BASE/fixtures/$ID -H 'Authorization: Bearer <writer token>'" \
    -X DELETE "$BASE/fixtures/$ID" -H "Authorization: Bearer $W"
  req "curl -X DELETE $BASE/fixtures/$ID -H 'Authorization: Bearer <moderator token>'" \
    -X DELETE "$BASE/fixtures/$ID" -H "Authorization: Bearer $M"
}
part_list() {
  echo "== 6. GET /fixtures?limit=3 as reader -> 200 =="
  R=$(token s3319_reader "$READER_PASSWORD")
  req "curl '$BASE/fixtures?limit=3' -H 'Authorization: Bearer <reader token>'" "$BASE/fixtures?limit=3" -H "Authorization: Bearer $R"
}
run() {
  echo "---- hw7 part 1 [$1] $(date '+%Y-%m-%d %H:%M:%S %Z') ----"
  case "$1" in
    login) part_login ;; me) part_me ;; invalid) part_invalid ;;
    create) part_create ;; delete) part_delete ;; list) part_list ;;
    all) part_login; part_me; part_invalid; part_create; part_delete; part_list ;;
    *) echo "usage: $0 [login|me|invalid|create|delete|list|all]"; exit 1 ;;
  esac
}
run "${1:-all}" 2>&1 | tee -a "$LOG"