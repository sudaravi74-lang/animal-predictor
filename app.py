import streamlit as st
import requests
import hashlib
import json

from PIL import Image
from google import genai


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="Animal Encyclopedia AI",
    page_icon="🐾",
    layout="wide"
)

st.title("🐾 Animal Encyclopedia AI")
st.write(
    "Identify animals from images or search the biodiversity database."
)


# =========================================================
# SESSION STATE
# =========================================================

if "image_bytes" not in st.session_state:
    st.session_state.image_bytes = None

if "image_name" not in st.session_state:
    st.session_state.image_name = None

if "image_hash" not in st.session_state:
    st.session_state.image_hash = None

if "ai_result" not in st.session_state:
    st.session_state.ai_result = None

if "database_taxon" not in st.session_state:
    st.session_state.database_taxon = None

if "database_observations" not in st.session_state:
    st.session_state.database_observations = []

if "database_loaded" not in st.session_state:
    st.session_state.database_loaded = False


# =========================================================
# GEMINI
# =========================================================

try:

    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

except Exception:

    gemini_client = None


# =========================================================
# iNATURALIST
# =========================================================

INAT_API = "https://api.inaturalist.org/v1"


# =========================================================
# GEMINI IMAGE IDENTIFICATION
# =========================================================

@st.cache_data(
    show_spinner=False,
    ttl=3600
)
def identify_animal_cached(
    image_bytes,
    image_hash
):

    if gemini_client is None:

        return {
            "error": (
                "Gemini API key is not configured."
            )
        }


    prompt = """
You are an expert animal and wildlife identification assistant.

Analyze the uploaded image carefully.

Identify the animal visible in the image.

Return ONLY valid JSON:

{
  "animal": "common name",
  "scientific_name": "scientific name if reasonably identifiable",
  "confidence": 0,
  "reason": "short visual explanation"
}

Rules:

- Do NOT restrict the answer to a predefined list.
- The animal can be any species.
- If the image shows a rabbit, identify it as rabbit.
- If it shows a horse, identify it as horse.
- If it shows a monkey, identify it as monkey.
- If it shows a bird, identify the bird if possible.
- If exact species identification is uncertain, give the broader
  animal name instead.
- Never invent a scientific name.
- Confidence must be between 0 and 100.
"""


    try:

        image = Image.open(
            __import__("io").BytesIO(image_bytes)
        ).convert("RGB")


        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                prompt,
                image
            ]
        )


        text = response.text.strip()

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()


        result = json.loads(text)

        return result


    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
# iNATURALIST TAXON SEARCH
# =========================================================

@st.cache_data(
    show_spinner=False,
    ttl=3600
)
def search_taxon_cached(
    animal_name
):

    try:

        response = requests.get(
            f"{INAT_API}/taxa/autocomplete",
            params={
                "q": animal_name,
                "per_page": 5
            },
            timeout=15
        )


        if response.status_code != 200:
            return None


        results = response.json().get(
            "results",
            []
        )


        if not results:
            return None


        preferred_groups = [
            "Mammalia",
            "Aves",
            "Reptilia",
            "Amphibia",
            "Actinopterygii",
            "Insecta",
            "Arachnida",
            "Mollusca"
        ]


        for result in results:

            if result.get(
                "iconic_taxon_name"
            ) in preferred_groups:

                return result


        return results[0]


    except Exception:

        return None


# =========================================================
# iNATURALIST OBSERVATIONS
# =========================================================

@st.cache_data(
    show_spinner=False,
    ttl=3600
)
def get_observations_cached(
    taxon_id
):

    try:

        response = requests.get(
            f"{INAT_API}/observations",
            params={
                "taxon_id": taxon_id,
                "photos": "true",
                "per_page": 6,
                "order_by": "votes",
                "order": "desc",
                "quality_grade": "research"
            },
            timeout=20
        )


        if response.status_code != 200:
            return []


        return response.json().get(
            "results",
            []
        )


    except Exception:

        return []


# =========================================================
# PHOTO URL
# =========================================================

def get_large_photo_url(photo):

    url = photo.get("url")

    if not url:
        return None


    replacements = [
        ("/square.", "/large."),
        ("/small.", "/large."),
        ("/medium.", "/large.")
    ]


    for old, new in replacements:

        url = url.replace(
            old,
            new
        )


    return url


# =========================================================
# DISPLAY DATABASE RESULT
# =========================================================

def display_database_result(
    taxon,
    observations
):

    if not taxon:

        st.warning(
            "No matching species information was found."
        )

        return


    common_name = taxon.get(
        "preferred_common_name"
    )

    scientific_name = taxon.get(
        "name",
        "Unknown"
    )

    rank = taxon.get(
        "rank",
        "Unknown"
    )

    group = taxon.get(
        "iconic_taxon_name",
        "Unknown"
    )


    st.divider()

    st.header(
        f"🌍 {common_name or scientific_name}"
    )


    st.write(
        f"**Scientific name:** {scientific_name}"
    )

    st.write(
        f"**Taxonomic rank:** {rank}"
    )

    st.write(
        f"**Major group:** {group}"
    )


    # -----------------------------------------------------
    # MAIN DATABASE PHOTO
    # -----------------------------------------------------

    default_photo = taxon.get(
        "default_photo"
    )


    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
        )


        if photo_url:

            st.image(
                photo_url,
                caption="iNaturalist",
                use_container_width=True
            )


    # -----------------------------------------------------
    # MORE PHOTOS
    # -----------------------------------------------------

    photo_urls = []


    for observation in observations:

        photos = observation.get(
            "photos",
            []
        )


        for photo in photos:

            photo_url = get_large_photo_url(
                photo
            )


            if photo_url:

                photo_urls.append(
                    photo_url
                )


            if len(photo_urls) >= 6:
                break


        if len(photo_urls) >= 6:
            break


    if photo_urls:

        st.subheader(
            "📸 More photographs"
        )

        st.image(
            photo_urls,
            use_container_width=True
        )


    # -----------------------------------------------------
    # SOURCE
    # -----------------------------------------------------

    taxon_id = taxon.get("id")


    if taxon_id:

        st.markdown(
            f"[🌐 View species on iNaturalist]"
            f"(https://www.inaturalist.org/taxa/{taxon_id})"
        )


# =========================================================
# SIDEBAR / MODE
# =========================================================

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

    st.header(
        "📷 Identify an Animal"
    )


    # -----------------------------------------------------
    # NEW IMAGE BUTTON
    # -----------------------------------------------------

    if st.button(
        "🗑️ New Image"
    ):

        st.session_state.image_bytes = None
        st.session_state.image_name = None
        st.session_state.image_hash = None
        st.session_state.ai_result = None
        st.session_state.database_taxon = None
        st.session_state.database_observations = []
        st.session_state.database_loaded = False

        st.rerun()


    uploaded_file = st.file_uploader(
        "Upload an animal photograph",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )


    # -----------------------------------------------------
    # SAVE UPLOADED IMAGE
    # -----------------------------------------------------

    if uploaded_file is not None:

        new_bytes = uploaded_file.getvalue()

        new_hash = hashlib.sha256(
            new_bytes
        ).hexdigest()


        if (
            st.session_state.image_hash
            != new_hash
        ):

            st.session_state.image_bytes = new_bytes

            st.session_state.image_name = (
                uploaded_file.name
            )

            st.session_state.image_hash = new_hash

            st.session_state.ai_result = None

            st.session_state.database_taxon = None

            st.session_state.database_observations = []

            st.session_state.database_loaded = False


    # -----------------------------------------------------
    # DISPLAY SAVED IMAGE
    # -----------------------------------------------------

    if st.session_state.image_bytes:

        image = Image.open(
            __import__("io").BytesIO(
                st.session_state.image_bytes
            )
        ).convert("RGB")


        st.image(
            image,
            caption="Uploaded Image",
            use_container_width=True
        )


        # =================================================
        # IDENTIFY BUTTON
        # =================================================

        if st.session_state.ai_result is None:

            if st.button(
                "🔍 Identify Animal"
            ):

                with st.spinner(
                    "AI is identifying the animal..."
                ):

                    result = identify_animal_cached(
                        st.session_state.image_bytes,
                        st.session_state.image_hash
                    )


                st.session_state.ai_result = result

                st.rerun()


        # =================================================
        # SHOW AI RESULT
        # =================================================

        if st.session_state.ai_result:

            result = st.session_state.ai_result


            if "error" in result:

                st.error(
                    f"AI identification error: "
                    f"{result['error']}"
                )


            else:

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
                    f"🐾 Identified Animal: "
                    f"**{animal.title()}**"
                )


                st.metric(
                    "AI confidence",
                    f"{confidence}%"
                )


                if scientific_name:

                    st.write(
                        f"🔬 **Possible scientific name:** "
                        f"{scientific_name}"
                    )


                if reason:

                    st.write(
                        f"**Why:** {reason}"
                    )


                # =========================================
                # DATABASE BUTTON
                # =========================================

                if not st.session_state.database_loaded:

                    if st.button(
                        "🌍 Find Species Information & Photos"
                    ):

                        with st.spinner(
                            "Searching biodiversity database..."
                        ):

                            taxon = None


                            if scientific_name:

                                taxon = (
                                    search_taxon_cached(
                                        scientific_name
                                    )
                                )


                            if not taxon:

                                taxon = (
                                    search_taxon_cached(
                                        animal
                                    )
                                )


                            observations = []


                            if taxon:

                                observations = (
                                    get_observations_cached(
                                        taxon.get("id")
                                    )
                                )


                            st.session_state.database_taxon = (
                                taxon
                            )

                            st.session_state.database_observations = (
                                observations
                            )

                            st.session_state.database_loaded = True

                            st.rerun()


                # =========================================
                # DATABASE RESULT
                # =========================================

                if st.session_state.database_loaded:

                    display_database_result(
                        st.session_state.database_taxon,
                        st.session_state.database_observations
                    )


# =========================================================
# SEARCH ANIMAL
# =========================================================

elif mode == "🔎 Search Animal":

    st.header(
        "🔎 Search Animal Database"
    )


    search_name = st.text_input(
        "Enter any animal name:",
        placeholder="Example: Snow Leopard"
    )


    if st.button(
        "🔎 Search"
    ):

        if not search_name.strip():

            st.warning(
                "Please enter an animal name."
            )

        else:

            with st.spinner(
                "Searching biodiversity database..."
            ):

                taxon = search_taxon_cached(
                    search_name.strip()
                )


                observations = []


                if taxon:

                    observations = (
                        get_observations_cached(
                            taxon.get("id")
                        )
                    )


            display_database_result(
                taxon,
                observations
        )
