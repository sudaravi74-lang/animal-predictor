import streamlit as st
import requests
import hashlib
import json
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


# =========================================================
# CUSTOM STYLE
# =========================================================

st.markdown("""
<style>

.main-title {
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    margin-bottom: 5px;
}

.subtitle {
    text-align: center;
    font-size: 18px;
    color: #666;
    margin-bottom: 30px;
}

.option-card {
    border: 2px solid #e2e2e2;
    border-radius: 18px;
    padding: 25px;
    text-align: center;
    min-height: 190px;
    background: #fafafa;
    margin-bottom: 15px;
}

.option-icon {
    font-size: 48px;
}

.option-title {
    font-size: 24px;
    font-weight: 700;
    margin-top: 10px;
}

.option-text {
    font-size: 16px;
    color: #666;
    margin-top: 8px;
}

.section-title {
    text-align: center;
    font-size: 30px;
    font-weight: 700;
    margin-top: 20px;
    margin-bottom: 20px;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "page": "home",
    "image_bytes": None,
    "image_name": None,
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
# GEMINI MODELS
# =========================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
]


def is_temporary_error(error_text):

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

    return any(
        code in error_upper
        for code in temporary_codes
    )


def identify_with_model(
    image_bytes,
    model_name
):

    image = Image.open(
        BytesIO(image_bytes)
    )

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
- Keep the reason short.
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

            error_text = str(e)

            errors.append(
                f"{model_name}: {error_text}"
            )

            # Try the next available model
            if is_temporary_error(
                error_text
            ):
                continue

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


@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def search_taxon_cached(
    animal_name
):

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

        results = data.get(
            "results",
            []
        )

        if not results:
            return None

        animal_lower = (
            animal_name
            .lower()
            .strip()
        )

        # Prefer exact match
        for taxon in results:

            preferred = (
                taxon.get(
                    "preferred_common_name"
                )
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

        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_observations_cached(
    taxon_id
):

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

        return data.get(
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
# DISPLAY iNATURALIST RESULT
# =========================================================

def display_database_result(
    taxon,
    observations
):

    if not taxon:

        st.warning(
            "No biodiversity information was found."
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

        st.markdown(
            f"**Common name:** {common_name}"
        )

        st.markdown(
            f"**Scientific name:** "
            f"*{scientific_name}*"
        )

    with col2:

        st.markdown(
            f"**Taxonomic rank:** {rank}"
        )

        st.markdown(
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
            "📷 More iNaturalist Observations"
        )

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
            "https://www.inaturalist.org/taxa/"
            + str(taxon_id)
        )

        st.markdown(
            f"🔗 [View this animal on iNaturalist]"
            f"({inat_url})"
        )


# =========================================================
# HOME PAGE
# =========================================================

def show_home():

    st.markdown(
        '<div class="main-title">🐾 Animal Encyclopedia AI</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'Identify animals with AI or explore biodiversity information from iNaturalist.'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-title">'
        'How do you want to explore?'
        '</div>',
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(
        2,
        gap="large"
    )

    with col1:

        st.markdown(
            """
            <div class="option-card">

                <div class="option-icon">📷</div>

                <div class="option-title">
                    Identify an Animal
                </div>

                <div class="option-text">
                    Upload a photo and let AI
                    identify the animal.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            "📷  IDENTIFY AN ANIMAL",
            use_container_width=True,
            type="primary"
        ):

            st.session_state.page = (
                "identify"
            )

            st.rerun()

    with col2:

        st.markdown(
            """
            <div class="option-card">

                <div class="option-icon">🔎</div>

                <div class="option-title">
                    Search an Animal
                </div>

                <div class="option-text">
                    Search any animal and
                    explore its biodiversity information.
                </div>

            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            "🔎  SEARCH AN ANIMAL",
            use_container_width=True
        ):

            st.session_state.page = (
                "search"
            )

            st.rerun()


# =========================================================
# IDENTIFY PAGE
# =========================================================

def show_identify():

    col_back, col_title = st.columns(
        [1, 5]
    )

    with col_back:

        if st.button(
            "← Home"
        ):

            st.session_state.page = (
                "home"
            )

            st.rerun()

    with col_title:

        st.header(
            "📷 Identify an Animal"
        )

    st.write(
        "Upload a clear photo of an animal."
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

    if uploaded_file is not None:

        new_bytes = (
            uploaded_file.getvalue()
        )

        new_hash = hashlib.sha256(
            new_bytes
        ).hexdigest()

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

        # Identify button
        if st.session_state.ai_result is None:

            if st.button(
                "🔍 IDENTIFY ANIMAL",
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
                        "The AI services are temporarily unavailable."
                    )

                    st.info(
                        "The app automatically tried multiple "
                        "AI models. Please try again shortly."
                    )

                    with st.expander(
                        "Technical details"
                    ):

                        st.code(
                            result["error"]
                        )

        # AI result
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

                st.markdown(
                    f"**Possible scientific name:** "
                    f"*{scientific_name}*"
                )

            if reason:

                st.markdown(
                    f"**Why:** {reason}"
                )

            # iNaturalist
            if not st.session_state.database_loaded:

                st.divider()

                st.subheader(
                    "🌍 Explore this animal"
                )

                st.write(
                    "Get species information and "
                    "photographs from iNaturalist."
                )

                if st.button(
                    "🌍 GET SPECIES INFORMATION",
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
            "📷 Upload an animal photo above to begin."
        )


# =========================================================
# SEARCH PAGE
# =========================================================

def show_search():

    col_back, col_title = st.columns(
        [1, 5]
    )

    with col_back:

        if st.button(
            "← Home"
        ):

            st.session_state.page = (
                "home"
            )

            st.rerun()

    with col_title:

        st.header(
            "🔎 Search Animal"
        )

    st.write(
        "Search for any animal directly in iNaturalist."
    )

    search_name = st.text_input(
        "Animal name",
        placeholder=(
            "Example: Rabbit, Tiger, Eagle, Frog..."
        )
    )

    if st.button(
        "🔎 SEARCH ANIMAL",
        type="primary",
        use_container_width=True
    ):

        if not search_name.strip():

            st.warning(
                "Please enter an animal name."
            )

        else:

            with st.spinner(
                "Searching iNaturalist..."
            ):

                taxon = (
                    search_taxon_cached(
                        search_name.strip()
                    )
                )

                if (
                    taxon
                    and not
        taxon.get(
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

                elif (
                    taxon
                    and taxon.get("error")
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
# PAGE ROUTER
# =========================================================

if st.session_state.page == "home":

    show_home()

elif st.session_state.page == "identify":

    show_identify()

elif st.session_state.page == "search":

    show_search()
