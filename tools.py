import ast
import re
try:
    from langchain_core.tools.retriever import create_retriever_tool
except (ImportError, ModuleNotFoundError):
    from langchain.tools.retriever import create_retriever_tool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_community.tools import GooglePlacesTool
from langchain.tools import BaseTool
from googlemaps import Client as GoogleMaps
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

load_dotenv()

google_places = GooglePlacesTool()
gmaps = GoogleMaps(os.getenv("GPLACES_API_KEY"))


class GeocodingTool(BaseTool):
    name: str = "google_maps_geocoding"
    description: str = "Useful for converting addresses or place names into geographic coordinates (lat/lon)"

    def _run(self, address):
        try:
            result = gmaps.geocode(address)
            if result:
                loc = result[0]["geometry"]["location"]
                return f"The coordinates for '{address}' are lat={loc['lat']}, lon={loc['lng']}"
            return "Unable to find coordinates for the specified location"
        except Exception as e:
            return f"An error occurred: {str(e)}"


class DirectionsInput(BaseModel):
    origin: str = Field(..., description="The starting point address or coordinates")
    destination: str = Field(..., description="The destination address or coordinates")
    mode: str = Field(
        default="driving",
        description="Travel mode: 'driving', 'walking', 'transit', or 'bicycling'"
    )


class DirectionsTool(BaseTool):
    name: str = "google_maps_directions"
    description: str = (
        "Useful for finding travel distances and durations between two locations. "
        "Call this once per travel mode: 'driving' for car, 'walking' for on foot, "
        "'transit' for public transit, 'bicycling' for bike."
    )
    args_schema: type = DirectionsInput

    def _run(self, origin, destination, mode="driving"):
        try:
            result = gmaps.directions(origin, destination, mode=mode)
            if not result:
                return f"Unable to find {mode} directions between the specified locations"

            leg = result[0]["legs"][0]
            distance = leg["distance"]["text"]
            duration = leg["duration"]["text"]

            if mode == "transit":
                steps = []
                for step in leg.get("steps", []):
                    travel_mode = step.get("travel_mode", "")
                    if travel_mode == "WALKING":
                        dist = step["distance"]["text"]
                        dur = step["duration"]["text"]
                        instruction = re.sub(r"<[^>]+>", " ", step.get("html_instructions", "Walk")).strip()
                        steps.append(f"Walk {dist} (~{dur}): {instruction}")
                    elif travel_mode == "TRANSIT":
                        td = step.get("transit_details", {})
                        dep_stop = td.get("departure_stop", {}).get("name", "unknown stop")
                        arr_stop = td.get("arrival_stop", {}).get("name", "unknown stop")
                        line = td.get("line", {})
                        bus_num = line.get("short_name") or line.get("name", "unknown route")
                        vehicle = td.get("vehicle", {}).get("type", "Transit").title()
                        num_stops = td.get("num_stops", "?")
                        headsign = td.get("headsign", "")
                        dep_time = td.get("departure_time", {}).get("text", "")
                        arr_time = td.get("arrival_time", {}).get("text", "")
                        steps.append(
                            f"Board {vehicle} #{bus_num} towards '{headsign}' at {dep_stop} "
                            f"(departs {dep_time}) — ride {num_stops} stop(s) — "
                            f"get off at {arr_stop} (arrives {arr_time})"
                        )
                steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps))
                return (
                    f"Transit route from {origin} to {destination} "
                    f"(total: {distance}, ~{duration}):\n{steps_text}"
                )

            mode_label = {
                "driving": "by car",
                "walking": "on foot",
                "bicycling": "by bike",
            }.get(mode, mode)
            return f"{distance}, approx. {duration} {mode_label}"
        except Exception as e:
            return f"An error occurred: {str(e)}"


directions_tool = DirectionsTool()
geocoding_tool = GeocodingTool()


def query_as_list(db, query):
    res = db.run(query)
    res = [el for sub in ast.literal_eval(res) for el in sub if el]
    return list(set(res))


def setup_tools(db, llm):
    agency_names = query_as_list(db, "SELECT agency_name FROM agencies")
    route_names = query_as_list(
        db,
        "SELECT route_long_name FROM routes WHERE route_long_name IS NOT NULL AND route_long_name <> '' LIMIT 5000"
    )

    all_names = list(set(agency_names + route_names))
    vector_db = FAISS.from_texts(all_names, OpenAIEmbeddings())
    retriever = vector_db.as_retriever(search_kwargs={"k": 5})
    retriever_tool = create_retriever_tool(
        retriever,
        name="search_proper_nouns",
        description=(
            "Use to look up the correct spelling of transit agency names and route names. "
            "Input is an approximate or partial name, output is the closest matching name in the database. "
            "Always use this before filtering on agency_name or route_long_name."
        ),
    )

    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()
    tools.append(retriever_tool)
    tools.append(google_places)
    tools.append(geocoding_tool)
    tools.append(directions_tool)
    return tools
