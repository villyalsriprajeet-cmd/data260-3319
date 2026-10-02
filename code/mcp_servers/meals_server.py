# HW5 Part 2A: "meals" MCP server for TheMealDB 
import logging
import sys
from typing import Annotated, Any
import httpx
try:
    from mcp.server.fastmcp import FastMCP 
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP  
    from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
# Constants
MEALDB_API_BASE = "https://www.themealdb.com/api/json/v1/1" 
REQUEST_TIMEOUT = 10.0  # seconds to wait for TheMealDB before giving up
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("meals")
# Initialize the FastMCP server
mcp = FastMCP("meals")
async def make_mealdb_request(path: str, params: dict[str, str]) -> list[dict[str, Any]] | None:
    """Call one TheMealDB endpoint and return its "meals" list (None means no matches)."""
    url = f"{MEALDB_API_BASE}/{path}"
    logger.info("GET %s %s", url, params)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()  
            payload = response.json() 
        except httpx.HTTPError as exc:
            logger.error("network error on %s: %s", path, exc)
            raise ToolError(f"TheMealDB request failed: {exc}") from exc
        except ValueError as exc:
            logger.error("invalid JSON from %s", path)
            raise ToolError("TheMealDB returned a response that is not valid JSON") from exc
    return payload.get("meals")
def format_summary(meal: dict[str, Any]) -> dict[str, Any]:
    """Shape used by search_meals_by_name."""
    return {"id": meal["idMeal"], "name": meal["strMeal"], "area": meal.get("strArea"),
            "category": meal.get("strCategory"), "thumb": meal.get("strMealThumb")}
def format_card(meal: dict[str, Any]) -> dict[str, Any]:
    """Small card used by meals_by_ingredient."""
    return {"id": meal["idMeal"], "name": meal["strMeal"], "thumb": meal.get("strMealThumb")}
def format_details(meal: dict[str, Any]) -> dict[str, Any]:
    """Full recipe used by meal_details and random_meal."""
    ingredients = []
    for n in range(1, 21):  
        name = (meal.get(f"strIngredient{n}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": (meal.get(f"strMeasure{n}") or "").strip()})
    return {"id": meal["idMeal"], "name": meal["strMeal"], "category": meal.get("strCategory"),
            "area": meal.get("strArea"), "instructions": meal.get("strInstructions"),
            "image": meal.get("strMealThumb"), "source": meal.get("strSource"),
            "youtube": meal.get("strYoutube"), "ingredients": ingredients}
@mcp.tool()
async def search_meals_by_name(query: Annotated[str, Field(min_length=1)],
                               limit: Annotated[int, Field(ge=1, le=25)] = 5) -> dict:
    """Search TheMealDB for meals by name.

    Args:
        query: Part of a meal name, e.g. "Arrabiata"
        limit: Maximum number of meals to return (1-25)
    """
    meals = await make_mealdb_request("search.php", {"s": query.strip()})
    if not meals:
        return {"results": [], "message": f"no matches for '{query}'"}  # clear, empty result
    results = [format_summary(m) for m in meals[:limit]]
    return {"count": len(results), "results": results} 
@mcp.tool()
async def meals_by_ingredient(ingredient: Annotated[str, Field(min_length=1)],
                              limit: Annotated[int, Field(ge=1, le=50)] = 12) -> dict:
    """List meals that use a main ingredient.

    Args:
        ingredient: Main ingredient, e.g. "chicken"
        limit: Maximum number of meals to return (1-50)
    """
    meals = await make_mealdb_request("filter.php", {"i": ingredient.strip()})
    if not meals:
        return {"results": [], "message": f"no matches for ingredient '{ingredient}'"}
    results = [format_card(m) for m in meals[:limit]]
    return {"count": len(results), "results": results}
@mcp.tool()
async def random_meal() -> dict:
    """Return one random meal with its full recipe."""
    meals = await make_mealdb_request("random.php", {})
    if not meals:
        return {"message": "no matches"}
    return format_details(meals[0])
@mcp.tool()
async def meal_details(id: str | int) -> dict:
    """Look up one meal by its TheMealDB id and return the full recipe.

    Args:
        id: Meal id from a search result, e.g. 52771
    """
    meal_id = str(id).strip()
    if not meal_id.isdigit():
        raise ToolError(f"id must be a numeric meal id, got '{id}'")  # shown as a clean error in Inspector
    meals = await make_mealdb_request("lookup.php", {"i": meal_id})
    if not meals:
        return {"message": f"no meal with id {meal_id}"}
    return format_details(meals[0])
def main() -> None:
    mcp.run(transport="stdio") 
if __name__ == "__main__":
    main()