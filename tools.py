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


class DirectionsMapInput(BaseModel):
    origin_address: str = Field(..., description="Full address string of the origin")
    destination_address: str = Field(..., description="Full address string of the destination")
    origin_lat: float = Field(..., description="Latitude of the origin from geocoding")
    origin_lng: float = Field(..., description="Longitude of the origin from geocoding")


class GenerateDirectionsMapTool(BaseTool):
    name: str = "generate_directions_map"
    description: str = (
        "Generates an interactive Google Maps route map between two locations. "
        "Call this after getting directions for any travel question. "
        "Requires the origin and destination addresses and the origin lat/lng from geocoding."
    )
    args_schema: type = DirectionsMapInput

    def _run(self, origin_address, destination_address, origin_lat, origin_lng):
        import urllib.parse
        gmaps_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={urllib.parse.quote(origin_address)}"
            f"&destination={urllib.parse.quote(destination_address)}"
            "&travelmode=transit"
        )
        html = f"""<div id="map" style="height: 400px; width: 100%; border-radius: 10px; overflow: hidden;"></div>
<a href="{gmaps_url}" target="_blank" rel="noopener noreferrer"
   style="display:inline-flex; align-items:center; gap:8px; margin-top:10px; padding:10px 18px;
          background:#2563eb; color:#fff; text-decoration:none; border-radius:8px;
          font-size:0.9rem; font-weight:600;">
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
    <path d="M8 0a5.53 5.53 0 0 0-3.594 1.342c-.766.66-1.321 1.52-1.464 2.383C1.266 5.125 0 7.55 0 8a8 8 0 1 0 16 0c0-.45-1.266-2.875-2.942-4.275-.143-.863-.698-1.723-1.464-2.383A5.53 5.53 0 0 0 8 0zm0 1.5a4.03 4.03 0 0 1 2.607.976c.543.47.877 1.052.877 1.524 0 1.4-1.555 2.5-3.484 2.5-1.93 0-3.484-1.1-3.484-2.5 0-.472.334-1.053.877-1.524A4.03 4.03 0 0 1 8 1.5z"/>
  </svg>
  Open in Google Maps
</a>
<script>
function initMap() {{
    const map = new google.maps.Map(document.getElementById('map'), {{
        zoom: 7,
        center: {{ lat: {origin_lat}, lng: {origin_lng} }}
    }});
    const directionsService = new google.maps.DirectionsService();
    const directionsRenderer = new google.maps.DirectionsRenderer({{ map: map }});
    directionsService.route(
        {{
            origin: '{origin_address}',
            destination: '{destination_address}',
            travelMode: google.maps.TravelMode.TRANSIT
        }},
        function(result, status) {{
            if (status === 'OK') {{
                directionsRenderer.setDirections(result);
            }} else {{
                console.error('Directions failed: ' + status);
            }}
        }}
    );
}}
initMap();
</script>"""
        return f"```html\n{html}\n```"


directions_tool = DirectionsTool()
geocoding_tool = GeocodingTool()
directions_map_tool = GenerateDirectionsMapTool()


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
    tools.append(directions_map_tool)
    return tools
