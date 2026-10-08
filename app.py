import streamlit as st
import requests
import hashlib
import json
import time
from io import BytesIO
from PIL import Image
from google import genai


# =========================================================
# PAGE SETTINGS
# =========================================================

st.set_page_config(
    page_title="Animal Encyclopedia AI",
    page_icon="🐾",
    layout="wide"
)

st.title("🐾 Animal Encyclopedia AI")
st.caption("AI-powered animal identification + iNaturalist biodiversity database")


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "image_bytes": None,
    "image_name": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,
    "database_taxon": None,
    "database_observations": [],
    "database_loaded": False,
    "router_message": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# GEMINI SETUP
# =========================================================

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

except Exception:
    gemini_client = None


# =========================================================
# GEMINI MODEL ROUTER
# =========================================================
#
# The app tries the strongest Flash model first.
# If it temporarily fails with 503/429/etc.,
# it automatically tries another Flash model.
#
# This does NOT mean we can see Google's physical
# server load. Instead, we react to availability/errors.
# =========================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
]


def is_temporary_error(error_text):
    """Check whether an error looks temporary."""

    temporary_codes = [
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "408",
        "TIMEOUT",
        "500",
        "502",
        "504",
        "INTERNAL"
    ]

    error_upper = str(error_text).upper()

    return any(code in error_upper for code in temporary_codes)


def identify_with_model(image_bytes, model_name):
    """Ask one Gemini model to identify the animal."""

    image = Image.open(BytesIO(image_bytes))

    prompt = """
Identify the animal in this image.

Return ONLY valid JSON in exactly this format:

{
  "animal": "common animal name",
  "scientific_name": "scientific name if reasonably identifiable, otherwise empty string",
  "confidence": 0,
  "reason": "short explanation based only on visible features"
}

Rules:

- Identify the animal visible in the image.
- Do not invent a species if the image does not allow species-level identification.
- If only the broader animal group is clear, give the broader common name.
- Confidence must be a number from 0 to 100.
- Keep reason short.
- Return JSON only.
"""

    response = gemini_client.models.generate_content(
        model=model_name,
        contents=[
            prompt,
            image
        ]
    )

    text = response.text.strip()

    # Remove markdown JSON fences if Gemini adds them
    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    result = json.loads(text)

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def identify_animal_cached(image_bytes, image_hash):
    """
    Cached identification.

    Same image won't need another Gemini request
    for one hour when the server cache is available.
    """

    if gemini_client is None:
        return {
            "success": False,
            "error": "GEMINI_API_KEY is missing or invalid.",
            "model": None
        }

    errors = []

    for model_name in GEMINI_MODELS:

        try:

            result = identify_with_model(
                image_bytes,
                model_name
            )

            return {
                "success": True,
                "result": result,
                "model": model_name,
                "error": None
            }

        except Exception as e:

            error_text = str(e)
            errors.append(
                f"{model_name}: {error_text}"
            )

            # Temporary error:
            # move to next model
            if is_temporary_error(error_text):

                continue

            # Other errors:
            # also try the next model, because a different
            # model may still work.
            continue

    return {
        "success": False,
        "error": "\n\n".join(errors),
        "model": None
    }


# =========================================================
# iNATURALIST
# =========================================================

INATURALIST_TAXA_URL = (
    "https://api.inaturalist.org/v1/taxa/autocomplete"
)

INATURALIST_OBSERVATIONS_URL = (
    "https://api.inaturalist.org/v1/observations"
)


@st.cache_data(ttl=3600, show_spinner=False)
def search_taxon_cached(animal_name):

    try:

        response = requests.get(
            INATURALIST_TAXA_URL,
            params={
                "q": animal_name,
                "per_page": 10
            },
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        if not results:
            return None

        # Prefer exact/common-name matching where possible
        animal_lower = animal_name.lower().strip()

        for taxon in results:

            preferred = (
                taxon.get("preferred_common_name")
                or ""
            ).lower()

            name = (
                taxon.get("name")
                or ""
            ).lower()

            if (
                preferred == animal_lower
                or name == animal_lower
            ):
                return taxon

        # Otherwise use first relevant result
        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


@st.cache_data(ttl=3600, show_spinner=False)
def get_observations_cached(taxon_id):

    try:

        response = requests.get(
            INATURALIST_OBSERVATIONS_URL,
            params={
                "taxon_id": taxon_id,
                "photos": "true",
                "quality_grade": "research",
                "order_by": "votes",
                "order": "desc",
                "per_page": 6
            },
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        return data.get("results", [])

    except Exception:
        return []


def get_large_photo_url(photo):

    if not photo:
        return None

    url = photo.get("url")

    if not url:
        return None

    # Convert iNaturalist thumbnail URLs
    # to larger versions.
    url = url.replace(
        "/square.",
        "/large."
    )

    url = url.replace(
        "/small.",
        "/large."
    )

    url = url.replace(
        "/medium.",
        "/large."
    )

    return url


# =========================================================
# DISPLAY iNATURALIST RESULT
# =========================================================

def display_database_result(taxon, observations):

    if not taxon:
        st.warning(
            "No biodiversity information was found on iNaturalist."
        )
        return

    if taxon.get("error"):
        st.error(
            "iNaturalist error: "
            + str(taxon["error"])
        )
        return

    common_name = (
        taxon.get("preferred_common_name")
        or taxon.get("name")
        or "Unknown"
    )

    scientific_name = (
        taxon.get("name")
        or "Unknown"
    )

    rank = (
        taxon.get("rank")
        or "Unknown"
    )

    iconic_taxon = (
        taxon.get("iconic_taxon_name")
        or "Unknown"
    )

    st.divider()

    st.subheader("🌍 iNaturalist Information")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"**Common name:** {common_name}"
        )

        st.markdown(
            f"**Scientific name:** *{scientific_name}*"
        )

    with col2:
        st.markdown(
            f"**Taxonomic rank:** {rank}"
        )

        st.markdown(
            f"**Major group:** {iconic_taxon}"
        )

    # Main taxon photo
    default_photo = taxon.get("default_photo")

    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
        )

        if photo_url:

            st.subheader("📸 Species Photograph")

            st.image(
                photo_url,
                use_container_width=True
            )

    # Observation photos
    if observations:

        st.subheader("📷 More iNaturalist Observations")

        photo_urls = []

        for observation in observations:

            photos = observation.get(
                "photos",
                []
            )

            if photos:

                photo_url = get_large_photo_url(
                    photos[0]
                )

                if photo_url:
                    photo_urls.append(
                        photo_url
                    )

        if photo_urls:

            st.image(
                photo_urls,
                use_container_width=True
            )

    # iNaturalist link
    taxon_id = taxon.get("id")

    if taxon_id:

        inat_url = (
            f"https://www.inaturalist.org/taxa/"
            f"{taxon_id}"
        )

        st.markdown(
            f"🔗 [View this taxon on iNaturalist]({inat_url})"
        )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("🐾 Animal Encyclopedia")

    st.write(
        "Identify animals using AI and "
        "retrieve biodiversity information "
        "from iNaturalist."
    )

    st.divider()

    mode = st.radio(
        "Choose an option:",
        [
            "📷 Identify from Image",
            "🔎 Search Animal"
        ]
    )


# =========================================================
# IMAGE IDENTIFICATION
# =========================================================

if mode == "📷 Identify from Image":

    st.header("📷 Identify an Animal")

    # -----------------------------------------------------
    # NEW IMAGE BUTTON
    # -----------------------------------------------------

    if st.button("🗑️ New Image"):

        st.session_state.image_bytes = None
        st.session_state.image_name = None
        st.session_state.image_hash = None
        st.session_state.ai_result = None
        st.session_state.ai_model_used = None
        st.session_state.database_taxon = None
        st.session_state.database_observations = []
        st.session_state.database_loaded = False
        st.session_state.router_message = None

        st.rerun()

    # -----------------------------------------------------
    # UPLOADER
    # -----------------------------------------------------

    uploaded_file = st.file_uploader(
        "Upload an animal image",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )

    if uploaded_file is not None:

        new_bytes = uploaded_file.getvalue()

        new_hash = hashlib.sha256(
            new_bytes
        ).hexdigest()

        # Only reset results if this is a genuinely
        # different image.
        if (
            st.session_state.image_hash
            != new_hash
        ):

            st.session_state.image_bytes = (
                new_bytes
            )

            st.session_state.image_name = (
                uploaded_file.name
            )

            st.session_state.image_hash = (
                new_hash
            )

            st.session_state.ai_result = None
            st.session_state.ai_model_used = None

            st.session_state.database_taxon = None
            st.session_state.database_observations = []
            st.session_state.database_loaded = False

    # -----------------------------------------------------
    # SHOW STORED IMAGE
    # -----------------------------------------------------

    if st.session_state.image_bytes:

        image = Image.open(
            BytesIO(
                st.session_state.image_bytes
            )
        )

        st.image(
            image,
            caption="Uploaded Image",
            use_container_width=True
        )

        # -------------------------------------------------
        # IDENTIFY
        # -------------------------------------------------

        if st.session_state.ai_result is None:

            if st.button(
                "🔍 Identify Animal",
                type="primary"
            ):

                with st.spinner(
                    "AI is identifying the animal..."
                ):

                    result = identify_animal_cached(
                        st.session_state.image_bytes,
                        st.session_state.image_hash
                    )

                if result["success"]:

                    st.session_state.ai_result = (
                        result["result"]
                    )

                    st.session_state.ai_model_used = (
                        result["model"]
                    )

                    st.session_state.router_message = (
                        f"Identified using {result['model']}"
                    )

                    st.rerun()

                else:

                    st.error(
                        "The AI services are temporarily "
                        "unavailable."
                    )

                    st.info(
                        "The app automatically tried "
                        "multiple Gemini Flash models. "
                        "Please try again in a moment."
                    )

                    with st.expander(
                        "Technical details"
                    ):
                        st.code(
                            result["error"]
                        )

        # -------------------------------------------------
        # SHOW AI RESULT
        # -------------------------------------------------

        if st.session_state.ai_result:

            result = st.session_state.ai_result

            animal = result.get(
                "animal",
                "Unknown"
            )

            scientific_name = result.get(
                "scientific_name",
                ""
            )

            confidence = result.get(
                "confidence",
                0
            )

            reason = result.get(
                "reason",
                ""
            )

            st.success(
                f"🐾 Identified Animal: **{animal}**"
            )

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "AI Confidence",
                    f"{confidence}%"
                )

            with col2:

                if st.session_state.ai_model_used:

                    st.metric(
                        "AI Model",
                        st.session_state.ai_model_used
                    )

            if scientific_name:

                st.markdown(
                    f"**Possible scientific name:** "
                    f"*{scientific_name}*"
                )

            if reason:

                st.markdown(
                    f"**Why:** {reason}"
                )

            # -------------------------------------------------
            # iNATURALIST LOOKUP
            # -------------------------------------------------

            if not st.session_state.database_loaded:

                st.divider()

                st.subheader(
                    "🌍 Get Biodiversity Information"
                )

                st.write(
                    "Now that the animal has been "
                    "identified, iNaturalist can provide "
                    "species information and photographs."
                )

                if st.button(
                    "🌍 Find Species Information & Photos",
                    type="primary"
                ):

                    with st.spinner(
                        "Searching iNaturalist..."
                    ):

                        taxon = search_taxon_cached(
                            animal
                        )

                        if taxon and not taxon.get(
                            "error"
                        ):

                            taxon_id = taxon.get(
                                "id"
                            )

                            if taxon_id:

                                observations = (
                                    get_observations_cached(
                                        taxon_id
                                    )
                                )

                                st.session_state.database_taxon = (
                                    taxon
                                )

                                st.session_state.database_observations = (
                                    observations
                                )

                                st.session_state.database_loaded = (
                                    True
                                )

                    st.rerun()

            # -------------------------------------------------
            # SHOW DATABASE
            # -------------------------------------------------

            if st.session_state.database_loaded:

                display_database_result(
                    st.session_state.database_taxon,
                    st.session_state.database_observations
                )


# =========================================================
# SEARCH ANIMAL
# =========================================================

else:

    st.header("🔎 Search Animal")

    st.write(
        "Search iNaturalist directly. "
        "You are not limited to a fixed list of animals."
    )

    search_name = st.text_input(
        "Enter an animal name",
        placeholder="Example: Rabbit, Tiger, Eagle, Frog..."
    )

    if st.button(
        "🔎 Search iNaturalist",
        type="primary"
    ):

        if not search_name.strip():

            st.warning(
                "Please enter an animal name."
            )

        else:

            with st.spinner(
                "Searching iNaturalist..."
            ):

                taxon = search_taxon_cached(
                    search_name.strip()
                )

                if taxon and not taxon.get(
                    "error"
                ):

                    taxon_id = taxon.get(
                        "id"
                    )

                    observations = []

                    if taxon_id:

                        observations = (
                            get_observations_cached(
                                taxon_id
                            )
                        )

                    display_database_result(
                        taxon,
                        observations
                    )

                elif taxon and taxon.get(
                    "error"
                ):

                    st.error(
                        "iNaturalist error: "
                        + str(taxon["error"])
                    )

                else:

                    st.warning(
                        "No matching taxon was found."
    )
