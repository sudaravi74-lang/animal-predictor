import streamlit as st
import requests
import hashlib
import json
import time
import re
from io import BytesIO
from PIL import Image
from google import genai


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Nature Encyclopedia AI",
    page_icon="🌍",
    layout="wide"
)


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "page": "home",

    # Photo identification
    "image_bytes": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,

    # Species
    "selected_taxon": None,
    "selected_observations": [],
    "selected_eol": None,

    # Search
    "search_name": "",

    # Home
    "home_nature_image": None,
}

for key, value in defaults.items():

    if key not in st.session_state:

        st.session_state[key] = value


# =========================================================
# iNATURALIST API
# =========================================================

INAT_TAXA_URL = (
    "https://api.inaturalist.org/v1/taxa/autocomplete"
)

INAT_OBSERVATIONS_URL = (
    "https://api.inaturalist.org/v1/observations"
)

HEADERS = {
    "User-Agent": "Nature-Encyclopedia-AI/1.0"
}


# =========================================================
# iNATURALIST TAXON SEARCH
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def search_taxon_cached(search_name):

    try:

        response = requests.get(
            INAT_TAXA_URL,
            params={
                "q": search_name,
                "per_page": 10
            },
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        results = response.json().get(
            "results",
            []
        )

        if not results:

            return None

        search_lower = (
            search_name
            .strip()
            .lower()
        )

        # Exact match first
        for taxon in results:

            common_name = (
                taxon.get(
                    "preferred_common_name"
                )
                or ""
            ).lower()

            scientific_name = (
                taxon.get("name")
                or ""
            ).lower()

            if (
                common_name == search_lower
                or scientific_name == search_lower
            ):

                return taxon

        # Otherwise best result
        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
# iNATURALIST OBSERVATIONS
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def get_observations_cached(taxon_id):

    try:

        response = requests.get(
            INAT_OBSERVATIONS_URL,
            params={
                "taxon_id": taxon_id,
                "photos": "true",
                "quality_grade": "research",
                "order_by": "votes",
                "order": "desc",
                "per_page": 6
            },
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.json().get(
            "results",
            []
        )

    except Exception:

        return []


# =========================================================
# iNATURALIST PHOTO URL
# =========================================================

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
# ENCYCLOPEDIA OF LIFE
# =========================================================

EOL_SEARCH_URL = (
    "https://eol.org/api/search/1.0.json"
)

EOL_PAGES_URL = (
    "https://eol.org/api/pages/1.0.json"
)


# =========================================================
# CLEAN EOL TEXT
# =========================================================

def clean_eol_text(text):

    if not text:

        return ""

    # Remove HTML tags
    text = re.sub(
        r"<[^>]+>",
        " ",
        str(text)
    )

    # Basic HTML entities
    text = (
        text
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )

    # Remove extra spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# =========================================================
# EOL SEARCH
# =========================================================

@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def search_eol_cached(search_name):

    try:

        response = requests.get(
            EOL_SEARCH_URL,
            params={
                "q": search_name,
                "page": 1,
                "exact": "true"
            },
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        results = data.get(
            "results",
            []
        )

        # If exact search failed,
        # try broader search.
        if not results:

            response = requests.get(
                EOL_SEARCH_URL,
                params={
                    "q": search_name,
                    "page": 1
                },
                headers=HEADERS,
                timeout=20
            )

            response.raise_for_status()

            data = response.json()

            results = data.get(
                "results",
                []
            )

        if not results:

            return None

        search_lower = (
            search_name
            .strip()
            .lower()
        )

        # Exact title match
        for result in results:

            title = (
                str(
                    result.get("title")
                    or ""
                )
                .lower()
            )

            if title == search_lower:

                return result

        return results[0]

    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
# EOL PAGE
# =========================================================

@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def get_eol_page_cached(eol_id):

    try:

        response = requests.get(
            EOL_PAGES_URL,
            params={
                "id": eol_id,
                "details": "true",
                "images_per_page": 0,
                "videos_per_page": 0,
                "sounds_per_page": 0,
                "maps_per_page": 0,
                "texts_per_page": 20,
                "common_names": "true",
                "synonyms": "true",
                "references": "true",
                "taxonomy": "true",
                "language": "en"
            },
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except Exception as e:

        return {
            "error": str(e)
        }


# =========================================================
# ORGANIZE EOL INFORMATION
# =========================================================

def extract_eol_sections(page_data):

    sections = {

        "overview": [],

        "physical": [],

        "distribution": [],

        "life": [],

        "ecology": [],

        "other": []
    }

    objects = page_data.get(
        "dataObjects",
        []
    )

    for obj in objects:

        data_type = obj.get(
            "dataType"
        )

        if data_type not in [
            "http://purl.org/dc/dcmitype/Text",
            "Text"
        ]:

            continue

        description = clean_eol_text(
            obj.get("description")
        )

        if len(description) < 40:

            continue

        title = clean_eol_text(
            obj.get("title")
        ).lower()

        subjects = obj.get(
            "subjects"
        ) or []

        subject_text = " ".join(
            [
                str(x)
                for x in subjects
            ]
        ).lower()

        combined = (
            title
            + " "
            + subject_text
        )

        # Distribution / habitat
        if any(
            word in combined
            for word in [
                "distribution",
                "geographic",
                "range",
                "habitat"
            ]
        ):

            category = "distribution"

        # Physical
        elif any(
            word in combined
            for word in [
                "physical",
                "description",
                "morphology",
                "anatomy",
                "appearance",
                "identification"
            ]
        ):

            category = "physical"

        # Life / behaviour
        elif any(
            word in combined
            for word in [
                "behavior",
                "behaviour",
                "life history",
                "reproduction",
                "feeding",
                "diet"
            ]
        ):

            category = "life"

        # Ecology
        elif any(
            word in combined
            for word in [
                "ecology",
                "ecosystem",
                "ecological",
                "interaction"
            ]
        ):

            category = "ecology"

        # First unmatched text = overview
        elif not sections["overview"]:

            category = "overview"

        else:

            category = "other"

        entry = {

            "title": clean_eol_text(
                obj.get("title")
            ),

            "text": description,

            "source": obj.get(
                "source"
            ) or "",

            "license": obj.get(
                "license"
            ) or ""
        }

        sections[
            category
        ].append(entry)

    # Keep page readable
    for key in sections:

        sections[key] = sections[key][:4]

    return sections


# =========================================================
# EOL SOURCE URL
# =========================================================

def get_eol_source_url(eol_id):

    return (
        "https://eol.org/pages/"
        + str(eol_id)
    )


# =========================================================
# GEMINI SETUP
# =========================================================

try:

    GEMINI_API_KEY = st.secrets[
        "GEMINI_API_KEY"
    ]

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

    "gemini-3.6-flash"
]


# =========================================================
# GEMINI PHOTO IDENTIFICATION
# =========================================================

def identify_with_model(
    image_bytes,
    model_name
):

    image = Image.open(
        BytesIO(image_bytes)
    )

    prompt = """

Look carefully at this image.

Identify the main living organism.

It may be:

- an animal
- a plant
- another clearly identifiable living organism

For this application, focus mainly on animals and plants.

Return ONLY valid JSON:

{
  "type": "animal or plant",
  "common_name": "common name",
  "scientific_name": "scientific name if reasonably identifiable, otherwise empty string",
  "confidence": 0,
  "reason": "short explanation based on visible features"
}

Rules:

1. Do not invent a species.

2. If species-level identification is uncertain,
identify the broader organism.

3. Confidence must be between 0 and 100.

4. Keep the reason short.

5. Return JSON only.

"""

    response = (
        gemini_client
        .models
        .generate_content(
            model=model_name,
            contents=[
                prompt,
                image
            ]
        )
    )

    text = response.text.strip()

    # Remove Markdown code fences
    if text.startswith("```"):

        text = text.replace(
            "```json",
            "",
            1
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    # Find JSON if Gemini
    # accidentally adds text
    if not text.startswith("{"):

        start = text.find("{")

        end = text.rfind("}")

        if (
            start != -1
            and end != -1
        ):

            text = text[
                start:end + 1
            ]

    return json.loads(text)


# =========================================================
# IDENTIFICATION CACHE
# =========================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False
)
def identify_organism_cached(
    image_bytes,
    image_hash
):

    if gemini_client is None:

        return {

            "success": False,

            "error":
                "GEMINI_API_KEY is missing or invalid.",

            "model": None
        }

    errors = []

    for model_name in GEMINI_MODELS:

        for attempt in range(2):

            try:

                result = (
                    identify_with_model(
                        image_bytes,
                        model_name
                    )
                )

                return {

                    "success": True,

                    "result": result,

                    "model": model_name,

                    "error": None
                }

            except Exception as e:

                errors.append(
                    f"{model_name} "
                    f"attempt {attempt + 1}: "
                    f"{str(e)}"
                )

                if attempt == 0:

                    time.sleep(2)

    return {

        "success": False,

        "error": "\n\n".join(
            errors
        ),

        "model": None
    }


# =========================================================
# ORGANISM TYPE
# =========================================================

def determine_organism_type(
    taxon,
    ai_result=None
):

    if ai_result:

        ai_type = str(
            ai_result.get(
                "type",
                ""
            )
        ).lower()

        if ai_type in [
            "animal",
            "plant"
        ]:

            return ai_type

    major_group = str(
        taxon.get(
            "iconic_taxon_name",
            ""
        )
    ).lower()

    if major_group == "plantae":

        return "plant"

    if major_group == "animalia":

        return "animal"

    return "organism"


# =========================================================
# SPECIES PAGE
# =========================================================

def show_species_page(
    taxon,
    observations,
    ai_result=None
):

    if not taxon:

        st.warning(
            "Species information "
            "could not be found."
        )

        return

    if taxon.get("error"):

        st.error(
            "iNaturalist error: "
            + str(
                taxon["error"]
            )
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

    organism_type = (
        determine_organism_type(
            taxon,
            ai_result
        )
    )

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    if organism_type == "plant":

        st.title(
            f"🌱 {common_name}"
        )

    elif organism_type == "animal":

        st.title(
            f"🐾 {common_name}"
        )

    else:

        st.title(
            f"🌍 {common_name}"
        )

    st.markdown(
        f"### *{scientific_name}*"
    )

    # -----------------------------------------------------
    # BASIC INFORMATION
    # -----------------------------------------------------

    st.subheader(
        "📚 Basic Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            f"**Scientific name:** "
            f"*{scientific_name}*"
        )

        st.write(
            f"**Taxonomic rank:** "
            f"{rank}"
        )

    with col2:

        st.write(
            f"**Major group:** "
            f"{major_group}"
        )

        if organism_type == "plant":

            st.write(
                "**Type:** 🌱 Plant"
            )

        elif organism_type == "animal":

            st.write(
                "**Type:** 🐾 Animal"
            )

        else:

            st.write(
                "**Type:** 🌍 Living organism"
            )

    # -----------------------------------------------------
    # MAIN PHOTO
    # -----------------------------------------------------

    default_photo = (
        taxon.get(
            "default_photo"
        )
    )

    if default_photo:

        photo_url = (
            get_large_photo_url(
                default_photo
            )
        )

        if photo_url:

            st.subheader(
                "📸 Photograph"
            )

            st.image(
                photo_url,
                use_container_width=True
            )

    # -----------------------------------------------------
    # AI DETAILS
    # -----------------------------------------------------

    if ai_result:

        confidence = (
            ai_result.get(
                "confidence"
            )
        )

        if confidence is not None:

            st.write(
                f"**Identification confidence:** "
                f"{confidence}%"
            )

        reason = (
            ai_result.get(
                "reason",
                ""
            )
        )

        if reason:

            st.write(
                f"**Identification reason:** "
                f"{reason}"
            )

    # -----------------------------------------------------
    # EOL
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "🔬 More Information"
    )

    st.write(
        "This information is retrieved from "
        "the Encyclopedia of Life instead of "
        "being generated as facts by AI."
    )

    eol_result = (
        st.session_state.selected_eol
    )

    if st.button(
        "🔬 Load Encyclopedia Information",
        type="primary",
        use_container_width=True,
        key="load_eol_button"
    ):

        with st.spinner(
            "Finding encyclopedia information..."
        ):

            # First use scientific name
            eol_search = (
                search_eol_cached(
                    scientific_name
                )
            )

            # If not found,
            # try common name
            if (
                not eol_search
                or eol_search.get("error")
            ):

                eol_search = (
                    search_eol_cached(
                        scientific_name
                )
            )

            # If not found,
            # try common name
            if (
                not eol_search
                or eol_search.get("error")
            ):

                eol_search = (
                    search_eol_cached(
                        common_name
                    )
                )

            if (
                eol_search
                and not eol_search.get(
                    "error"
                )
            ):

                eol_id = (
                    eol_search.get(
                        "id"
                    )
                )

                if eol_id:

                    eol_page = (
                        get_eol_page_cached(
                            eol_id
                        )
                    )

                    st.session_state.selected_eol = {

                        "search": eol_search,

                        "page": eol_page
                    }

                    st.rerun()

                else:

                    st.error(
                        "EOL found a result "
                        "but no page ID."
                    )

            elif (
                eol_search
                and eol_search.get(
                    "error"
                )
            ):

                st.error(
                    "Encyclopedia of Life "
                    "could not be reached right now."
                )

                with st.expander(
                    "Technical details"
                ):

                    st.code(
                        str(
                            eol_search[
                                "error"
                            ]
                        )
                    )

            else:

                st.warning(
                    "No Encyclopedia of Life "
                    "page was found for this organism."
                )

    # -----------------------------------------------------
    # SHOW EOL INFORMATION
    # -----------------------------------------------------

    if eol_result:

        eol_page = (
            eol_result.get(
                "page",
                {}
            )
        )

        if eol_page.get(
            "error"
        ):

            st.error(
                "EOL page could not be loaded."
            )

        else:

            sections = (
                extract_eol_sections(
                    eol_page
                )
            )

            st.success(
                "Information source: "
                "Encyclopedia of Life"
            )

            eol_id = (
                eol_result
                .get("search", {})
                .get("id")
            )

            if eol_id:

                st.markdown(
                    "🔗 [Open the full "
                    "Encyclopedia of Life page]"
                    f"({get_eol_source_url(eol_id)})"
                )

            section_titles = [

                (
                    "overview",
                    "📖 Overview"
                ),

                (
                    "physical",
                    "🧬 Physical Description"
                ),

                (
                    "distribution",
                    "🌍 Distribution & Habitat"
                ),

                (
                    "life",
                    "🧠 Behaviour, Life History & Reproduction"
                ),

                (
                    "ecology",
                    "🌿 Ecology"
                ),

                (
                    "other",
                    "📚 Other Information"
                )
            ]

            displayed_any = False

            for (
                section_key,
                title
            ) in section_titles:

                entries = sections.get(
                    section_key,
                    []
                )

                if not entries:

                    continue

                displayed_any = True

                with st.expander(
                    title,
                    expanded=(
                        section_key
                        == "overview"
                    )
                ):

                    for entry in entries:

                        if entry["title"]:

                            st.markdown(
                                f"**{entry['title']}**"
                            )

                        st.write(
                            entry["text"]
                        )

                        if entry["source"]:

                            st.caption(
                                "Source: "
                                + str(
                                    entry["source"]
                                )
                            )

                        st.divider()

            if not displayed_any:

                st.warning(
                    "The EOL page exists, "
                    "but it did not return "
                    "readable text information."
                )

    # -----------------------------------------------------
    # MORE PHOTOS
    # -----------------------------------------------------

    if observations:

        st.divider()

        st.subheader(
            "📷 More iNaturalist Photographs"
        )

        photo_urls = []

        for observation in observations:

            photos = (
                observation.get(
                    "photos",
                    []
                )
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

    # -----------------------------------------------------
    # iNATURALIST SOURCE
    # -----------------------------------------------------

    taxon_id = (
        taxon.get("id")
    )

    if taxon_id:

        inat_url = (
            "https://www.inaturalist.org/taxa/"
            + str(taxon_id)
        )

        st.markdown(
            f"🔗 [View this taxon on iNaturalist]"
            f"({inat_url})"
        )


# =========================================================
# HOME
# =========================================================

def show_home():

    st.title(
        "🌍 Nature Encyclopedia AI"
    )

    st.subheader(
        "Explore the living world"
    )

    st.write(
        "Search for animals, plants and "
        "other living organisms, or identify "
        "one from a photograph."
    )

    st.divider()

    # -----------------------------------------------------
    # Example image
    # -----------------------------------------------------

    if (
        st.session_state.home_nature_image
        is None
    ):

        example_taxon = (
            search_taxon_cached(
                "tiger"
            )
        )

        if (
            example_taxon
            and not example_taxon.get(
                "error"
            )
        ):

            st.session_state.home_nature_image = (
                get_large_photo_url(
                    example_taxon.get(
                        "default_photo"
                    )
                )
            )

    # -----------------------------------------------------
    # TWO OPTIONS
    # -----------------------------------------------------

    col1, col2 = st.columns(
        2,
        gap="large"
    )
    # =====================================================
    # FLORA & FAUNA
    # =====================================================

    with col1:

        with st.container(
            border=True
        ):

            if (
                st.session_state
                .home_nature_image
            ):

                st.image(
                    st.session_state
                    .home_nature_image,
                    use_container_width=True
                )

            else:

                st.markdown(
                    "## 🌿"
                )

            st.subheader(
                "🌿 Explore Flora & Fauna"
            )

            st.write(
                "Search animals, plants and "
                "other living organisms in one place."
            )

            if st.button(
                "Explore Flora & Fauna",
                type="primary",
                use_container_width=True,
                key="explore_nature_button"
            ):

                st.session_state.page = (
                    "search"
                )

                st.session_state.search_name = ""

                st.session_state.selected_taxon = (
                    None
                )

                st.session_state.selected_observations = (
                    []
                )

                st.session_state.selected_eol = (
                    None
                )

                st.rerun()

    # =====================================================
    # PHOTO IDENTIFICATION
    # =====================================================

    with col2:

        with st.container(
            border=True
        ):

            st.markdown(
                "## 📷"
            )

            st.subheader(
                "Identify from Photo"
            )

            st.write(
                "Upload a photograph and let AI "
                "identify an animal or plant."
            )

            if st.button(
                "Identify from Photo",
                type="primary",
                use_container_width=True,
                key="photo_button"
            ):

                st.session_state.page = (
                    "identify"
                )

                st.rerun()

    st.divider()

    st.info(
        "🌿 Species and photographs are "
        "discovered through iNaturalist. "
        "Encyclopedia information is retrieved "
        "from the Encyclopedia of Life."
    )


# =========================================================
# SEARCH PAGE
# =========================================================

def show_search():

    if st.button(
        "← Home"
    ):

        st.session_state.page = (
            "home"
        )

        st.rerun()

    st.title(
        "🌿 Explore Flora & Fauna"
    )

    st.write(
        "Search for an animal, plant or "
        "other living organism by common "
        "or scientific name."
    )

    with st.form(
        "nature_search_form"
    ):

        search_name = st.text_input(
            "Search organism",
            value=(
                st.session_state.search_name
            ),
            placeholder=(
                "Example: Tiger, Rabbit, "
                "Mango, Neem..."
            )
        )

        submitted = (
            st.form_submit_button(
                "🔎 Search",
                use_container_width=True
            )
        )

    if submitted:

        if not search_name.strip():

            st.warning(
                "Please enter an organism name."
            )

            return

        st.session_state.search_name = (
            search_name.strip()
        )

        with st.spinner(
            "Finding this organism..."
        ):

            taxon = (
                search_taxon_cached(
                    search_name.strip()
                )
            )

            if (
                taxon
                and not taxon.get(
                    "error"
                )
            ):

                taxon_id = (
                    taxon.get("id")
                )

                observations = []

                if taxon_id:

                    observations = (
                        get_observations_cached(
                            taxon_id
                        )
                    )

                st.session_state.selected_taxon = (
                    taxon
                )

                st.session_state.selected_observations = (
                    observations
                )

                st.session_state.selected_eol = (
                    None
                )

                st.rerun()

            elif (
                taxon
                and taxon.get("error")
            ):

                st.error(
                    "iNaturalist error: "
                    + str(
                        taxon["error"]
                    )
                )

            else:

                st.warning(
                    "No matching organism was found. "
                    "Try another common or scientific name."
                )

    # Show species
    if (
        st.session_state.selected_taxon
    ):

        show_species_page(

            st.session_state.selected_taxon,

            st.session_state
            .selected_observations
        )


# =========================================================
# PHOTO IDENTIFICATION PAGE
# =========================================================

def show_identify():

    if st.button(
        "← Home"
    ):

        st.session_state.page = (
            "home"
        )

        st.rerun()

    st.title(
        "📷 Identify an Animal or Plant"
    )

    st.write(
        "Upload a photograph and AI will "
        "try to identify the living organism."
    )

    uploaded_file = st.file_uploader(
        "Choose a photograph",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp"
        ]
    )

    if uploaded_file:

        image_bytes = (
            uploaded_file.getvalue()
        )

        image_hash = hashlib.sha256(
            image_bytes
        ).hexdigest()

        # New image
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

            st.session_state.ai_result = (
                None
            )

            st.session_state.ai_model_used = (
                None
            )

            st.session_state.selected_taxon = (
                None
            )

            st.session_state.selected_observations = (
                []
            )

            st.session_state.selected_eol = (
                None
            )

    # -----------------------------------------------------
    # DISPLAY IMAGE
    # -----------------------------------------------------

    if st.session_state.image_bytes:

        image = Image.open(
            BytesIO(
                st.session_state.image_bytes
            )
        )

        st.image(
            image,
            caption="Uploaded Photograph",
            use_container_width=True
        )

        # -------------------------------------------------
        # IDENTIFY
        # -------------------------------------------------

        if (
            st.session_state.ai_result
            is None
        ):

            if st.button(
                "🔍 Identify",
                type="primary",
                use_container_width=True
            ):

                with st.spinner(
                    "AI is examining the photograph..."
                ):

                    result = (
                        identify_organism_cached(

                            st.session_state
                            .image_bytes,

                            st.session_state
                            .image_hash
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
                        "The AI service is "
                        "temporarily unavailable."
                    )

                    st.info(
                        "The app automatically tried "
                        "the available Flash models."
                    )

                    with st.expander(
                        "Technical details"
                    ):

                        st.code(
                            result["error"]
                        )

        # -------------------------------------------------
        # AI RESULT
        # -------------------------------------------------

        if st.session_state.ai_result:

            result = (
                st.session_state.ai_result
            )

            organism_type = (
                result.get(
                    "type",
                    "organism"
                )
            )

            common_name = (
                result.get(
                    "common_name",
                    "Unknown"
                )
            )

            scientific_name = (
                result.get(
                    "scientific_name",
                    ""
                )
            )

            confidence = (
                result.get(
                    "confidence",
                    0
                )
            )

            reason = (
                result.get(
                    "reason",
                    ""
                )
            )

            if (
                organism_type.lower()
                == "plant"
            ):

                st.success(
                    f"🌱 Identified: "
                    f"**{common_name}**"
                )

            else:

                st.success(
                    f"🐾 Identified: "
                    f"**{common_name}**"
                )

            st.metric(
                "AI Confidence",
                f"{confidence}%"
            )

            if scientific_name:

                st.write(
                    f"**Scientific name:** "
                    f"*{scientific_name}*"
                )

            if reason:

                st.write(
                    f"**Why:** {reason}"
                )

            if st.session_state.ai_model_used:

                st.caption(
                    "AI model: "
                    + st.session_state
                    .ai_model_used
                )

            # -------------------------------------------------
            # FIND iNATURALIST
            # -------------------------------------------------

            if (
                st.session_state
                .selected_taxon
                is None
            ):

                if st.button(
                    "🌍 Find Species Information",
                    type="primary",
                    use_container_width=True
                ):

                    with st.spinner(
                        "Finding biodiversity information..."
                    ):

                        if scientific_name:

                            taxon = (
                                search_taxon_cached(
                                    scientific_name
                                )
                            )

                        else:

                            taxon = (
                                search_taxon_cached(
                                    common_name
                                )
                            )

                        if (
                            taxon
                            and not taxon.get(
                                "error"
                            )
                        ):

                            taxon_id = (
                                taxon.get(
                                    "id"
                                )
                            )

                            observations = []

                            if taxon_id:

                                observations = (
                                    get_observations_cached(
                                        taxon_id
                                    )
                                )

                            st.session_state.selected_taxon = (
                                taxon
                            )

                            st.session_state.selected_observations = (
                                observations
                            )

                            st.session_state.selected_eol = (
                                None
                            )

                            st.rerun()

                        else:

                            st.warning(
                                "The organism was identified, "
                                "but no matching iNaturalist "
                                "taxon was found."
                            )

            # -------------------------------------------------
            # SPECIES PAGE
            # -------------------------------------------------

            if (
                st.session_state
                .selected_taxon
            ):

                show_species_page(

                    st.session_state
                    .selected_taxon,

                    st.session_state
                    .selected_observations,

                    ai_result=result
                )

    else:

        st.info(
            "📷 Upload a photograph to begin."
        )


# =========================================================
# APP ROUTER
# =========================================================

if (
    st.session_state.page
    == "home"
):

    show_home()

elif (
    st.session_state.page
    == "search"
):

    show_search()

elif (
    st.session_state.page
    == "identify"
):

    show_identify()
                      
