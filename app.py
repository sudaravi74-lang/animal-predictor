import streamlit as st
import requests
import hashlib
import json
from io import BytesIO
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


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "page": "home",
    "image_bytes": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,
    "database_taxon": None,
    "database_observations": [],
    "database_loaded": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# iNATURALIST
# =========================================================

TAXA_URL = "https://api.inaturalist.org/v1/taxa/autocomplete"

OBSERVATIONS_URL = "https://api.inaturalist.org/v1/observations"


@st.cache_data(ttl=3600, show_spinner=False)
def search_taxon_cached(animal_name):

    try:

        response = requests.get(
            TAXA_URL,
            params={
                "q": animal_name,
                "per_page": 10
            },
            timeout=15
        )

        response.raise_for_status()

        results = response.json().get(
            "results",
            []
        )

        if not results:
            return None

        search_name = animal_name.lower().strip()

        # Prefer exact common/scientific name
        for taxon in results:

            common = (
                taxon.get(
                    "preferred_common_name"
                )
                or ""
            ).lower()

            scientific = (
                taxon.get("name")
                or ""
            ).lower()

            if (
                common == search_name
                or scientific == search_name
            ):
                return taxon

        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


@st.cache_data(ttl=3600, show_spinner=False)
def get_observations_cached(taxon_id):

    try:

        response = requests.get(
            OBSERVATIONS_URL,
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

        return response.json().get(
            "results",
            []
        )

    except Exception:
        return []


def get_large_photo_url(photo):

    if not photo:
        return None

    url = photo.get("url")

    if not url:
        return None

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
# GEMINI
# =========================================================

try:

    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

except Exception:

    gemini_client = None


GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
]


def identify_with_model(
    image_bytes,
    model_name
):

    image = Image.open(
        BytesIO(image_bytes)
    )

    prompt = """
Identify the animal in this image.

Return ONLY valid JSON:

{
  "animal": "common animal name",
  "scientific_name": "scientific name if reasonably identifiable, otherwise empty string",
  "confidence": 0,
  "reason": "short visual explanation"
}

Rules:

- Identify the visible animal.
- Do not invent a species.
- If species identification is uncertain, give the broader animal name.
- Confidence must be from 0 to 100.
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

    if text.startswith("```"):

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    return json.loads(text)


def is_temporary_error(error_text):

    error_text = str(
        error_text
    ).upper()

    temporary_codes = [
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "408",
        "TIMEOUT",
        "500",
        "502",
        "504"
    ]

    return any(
        code in error_text
        for code in temporary_codes
    )


@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def identify_animal_cached(
    image_bytes,
    image_hash
):

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

            errors.append(
                f"{model_name}: {str(e)}"
            )

            # Automatically move to another model
            continue

    return {
        "success": False,
        "error": "\n\n".join(errors),
        "model": None
    }


# =========================================================
# HOME PAGE
# =========================================================

def show_home():

    st.title("🐾 Animal Encyclopedia AI")

    st.markdown(
        "### Explore the animal world"
    )

    st.write(
        "Identify an animal from a photograph "
        "or search directly through biodiversity data."
    )

    st.divider()

    st.subheader(
        "What would you like to do?"
    )

    # -----------------------------------------------------
    # Get beautiful iNaturalist images for cards
    # -----------------------------------------------------

    rabbit = search_taxon_cached("rabbit")
    fox = search_taxon_cached("fox")

    rabbit_image = None
    fox_image = None

    if rabbit and not rabbit.get("error"):

        rabbit_photo = rabbit.get(
            "default_photo"
        )

        rabbit_image = get_large_photo_url(
            rabbit_photo
        )

    if fox and not fox.get("error"):

        fox_photo = fox.get(
            "default_photo"
        )

        fox_image = get_large_photo_url(
            fox_photo
        )

    # -----------------------------------------------------
    # TWO NATIVE STREAMLIT CARDS
    # -----------------------------------------------------

    col1, col2 = st.columns(
        2,
        gap="large"
    )

    # =====================================================
    # IDENTIFY CARD
    # =====================================================

    with col1:

        with st.container(border=True):

            if rabbit_image:

                st.image(
                    rabbit_image,
                    use_container_width=True
                )

            else:

                st.markdown(
                    "## 🐰"
                )

            st.subheader(
                "📷 Identify an Animal"
            )

            st.write(
                "Upload a photograph and let AI "
                "identify the animal."
            )

            if st.button(
                "📷 Identify an Animal",
                type="primary",
                use_container_width=True,
                key="identify_home"
            ):

                st.session_state.page = (
                    "identify"
                )

                st.rerun()

    # =====================================================
    # SEARCH CARD
    # =====================================================

    with col2:

        with st.container(border=True):

            if fox_image:

                st.image(
                    fox_image,
                    use_container_width=True
                )

            else:

                st.markdown(
                    "## 🦊"
                )

            st.subheader(
                "🔎 Search an Animal"
            )

            st.write(
                "Search any animal and explore "
                "its biodiversity information."
            )

            if st.button(
                "🔎 Search an Animal",
                use_container_width=True,
                key="search_home"
            ):

                st.session_state.page = (
                    "search"
                )

                st.rerun()

    st.divider()

    st.caption(
        "🌍 Biodiversity information and photographs "
        "are provided through iNaturalist."
    )


# =========================================================
# IDENTIFY PAGE
# =========================================================

def show_identify():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title("📷 Identify an Animal")

    st.write(
        "Upload a clear photograph of an animal."
    )

    uploaded_file = st.file_uploader(
        "Choose an animal image",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )

    if uploaded_file:

        image_bytes = uploaded_file.getvalue()

        image_hash = hashlib.sha256(
            image_bytes
        ).hexdigest()

        # Detect a new image
        if (
            st.session_state.image_hash
            != image_hash
        ):

            st.session_state.image_bytes = (
                image_bytes
            )

            st.session_state.image_hash = (
                image_hash
            )

            st.session_state.ai_result = None
            st.session_state.ai_model_used = None

            st.session_state.database_taxon = None
            st.session_state.database_observations = []
            st.session_state.database_loaded = False

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
        # AI IDENTIFICATION
        # -------------------------------------------------

        if st.session_state.ai_result is None:

            if st.button(
                "🔍 Identify Animal",
                type="primary",
                use_container_width=True
            ):

                with st.spinner(
                    "AI is identifying the animal..."
                ):

                    result = (
                        identify_animal_cached(
                            st.session_state.image_bytes,
                            st.session_state.image_hash
                        )
                    )

                if result["success"]:

                    st.session_state.ai_result = (
                        result["result"]
                    )

                    st.session_state.ai_model_used = (
                        result["model"]
                    )

                    st.rerun()

                else:

                    st.error(
                        "AI is temporarily unavailable."
                    )

                    st.info(
                        "The app automatically tried "
                        "multiple AI models. Please try again."
                    )

                    with st.expander(
                        "Technical details"
                    ):

                        st.code(
                            result["error"]
                        )

        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------

        if st.session_state.ai_result:

            result = (
                st.session_state.ai_result
            )

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
                f"🐾 Animal identified: **{animal}**"
            )

            st.metric(
                "AI Confidence",
                f"{confidence}%"
            )

            if scientific_name:

                st.write(
                    f"**Possible scientific name:** "
                    f"*{scientific_name}*"
                )

            if reason:

                st.write(
                    f"**Why:** {reason}"
                )

            # -------------------------------------------------
            # iNATURALIST
            # -------------------------------------------------

            if not st.session_state.database_loaded:

                st.divider()

                st.subheader(
                    "🌍 Explore this animal"
                )

                st.write(
                    "Get biodiversity information "
                    "and photographs from iNaturalist."
                )

                if st.button(
                    "🌍 Get Species Information",
                    type="primary",
                    use_container_width=True
                ):

                    with st.spinner(
                        "Searching iNaturalist..."
                    ):

                        taxon = (
                            search_taxon_cached(
                                animal
                            )
                        )

                        if (
                            taxon
                            and not taxon.get(
                                "error"
                            )
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

            if st.session_state.database_loaded:

                display_database_result(
                    st.session_state.database_taxon,
                    st.session_state.database_observations
                )

    else:

        st.info(
            "📷 Upload an animal photograph to begin."
        )


# =========================================================
# DATABASE RESULT
# =========================================================

def display_database_result(
    taxon,
    observations
):

    if not taxon:

        st.warning(
            "No information was found."
        )

        return

    if taxon.get("error"):

        st.error(
            "iNaturalist error: "
            + str(taxon["error"])
        )

        return

    common_name = (
        taxon.get(
            "preferred_common_name"
        )
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

    major_group = (
        taxon.get(
            "iconic_taxon_name"
        )
        or "Unknown"
    )

    st.divider()

    st.subheader(
        "🌍 iNaturalist Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            f"**Common name:** {common_name}"
        )

        st.write(
            f"**Scientific name:** "
            f"*{scientific_name}*"
        )

    with col2:

        st.write(
            f"**Taxonomic rank:** {rank}"
        )

        st.write(
            f"**Major group:** {major_group}"
        )

    # Main photo

    default_photo = taxon.get(
        "default_photo"
    )

    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
        )

        if photo_url:

            st.subheader(
                "📸 Species Photograph"
            )

            st.image(
                photo_url,
                use_container_width=True
            )

    # More photos

    if observations:

        st.subheader(
            "📷 More Photographs"
        )

        photo_urls = []

        for observation in observations:

            photos = observation.get(
                "photos",
                []
            )

            if photos:

                photo_url = (
                    get_large_photo_url(
                        photos[0]
                    )
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

    # iNaturalist page

    taxon_id = taxon.get("id")

    if taxon_id:

        url = (
            "https://www.inaturalist.org/taxa/"
            + str(taxon_id)
        )

        st.markdown(
            f"🔗 [View this animal on iNaturalist]({url})"
        )


# =========================================================
# SEARCH PAGE
# =========================================================

def show_search():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title("🔎 Search an Animal")

    st.write(
        "Search any animal directly through "
        "the iNaturalist biodiversity database."
    )

    animal_name = st.text_input(
        "Animal name",
        placeholder=(
            "Example: Rabbit, Tiger, Eagle, Frog..."
        )
    )

    if st.button(
        "🔎 Search Animal",
        type="primary",
        use_container_width=True
    ):

        if not animal_name.strip():

            st.warning(
                "Please enter an animal name."
            )

        else:

            with st.spinner(
                "Searching iNaturalist..."
            ):

                taxon = (
                    search_taxon_cached(
                        animal_name.strip()
                    )
                )

                if (
                    taxon
                    and not taxon.get(
                        "error"
                    )
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
                        "No matching animal was found."
                    )


# =========================================================
# APP ROUTER
# =========================================================

if st.session_state.page == "home":

    show_home()

elif st.session_state.page == "identify":

    show_identify()

elif st.session_state.page == "search":

    show_search()
