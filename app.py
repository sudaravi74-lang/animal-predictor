import streamlit as st
import requests
import hashlib
import json
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

    # Identification
    "image_bytes": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,

    # Species
    "selected_taxon": None,
    "selected_observations": [],
    "species_info": None,
    "species_info_loaded": False,

    # Search
    "search_name": "",

    # Home images
    "home_animal_image": None,
    "home_plant_image": None,
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
            headers={
                "User-Agent":
                "Nature-Encyclopedia-AI/1.0"
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

        search_lower = (
            search_name
            .strip()
            .lower()
        )

        # First try exact common/scientific match
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

        # Otherwise return best result
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
            headers={
                "User-Agent":
                "Nature-Encyclopedia-AI/1.0"
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


# =========================================================
# iNATURALIST PHOTO
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
#
# We use the current stable Flash models.
# If 3.8 is temporarily unavailable,
# the app can try 3.7.
# =========================================================

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
]


# =========================================================
# IDENTIFY ANIMAL OR PLANT
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

For this application, focus on animals and plants.

Return ONLY valid JSON in exactly this format:

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

    response = gemini_client.models.generate_content(
        model=model_name,
        contents=[
            prompt,
            image
        ]
    )

    text = response.text.strip()

    # Remove accidental markdown JSON fences
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


# =========================================================
# GEMINI IDENTIFICATION CACHE
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

            # Try the next model
            continue

    return {
        "success": False,
        "error": "\n\n".join(errors),
        "model": None
    }


# =========================================================
# GEMINI DETAILED SPECIES INFORMATION
# =========================================================
#
# This is NOT automatically generated when opening a species.
# It runs only when the user presses "More Information".
# =========================================================

@st.cache_data(
    ttl=86400,
    show_spinner=False
)
def generate_species_information(
    common_name,
    scientific_name,
    organism_type
):

    if gemini_client is None:

        return {
            "error":
                "Gemini API is not available."
        }

    prompt = f"""
Create an educational encyclopedia entry for:

Common name: {common_name}
Scientific name: {scientific_name}
Organism type: {organism_type}

Important:
- This is an educational biodiversity encyclopedia.
- Do not invent precise measurements when uncertain.
- Clearly indicate when information is approximate.
- Do not provide medical treatment or medicinal dosage.
- Do not claim that a species cures a disease.
- Do not invent scientific facts.

Return ONLY valid JSON:

{{
  "region": "...",
  "habitat": "...",
  "diet_or_growth": "...",
  "size": "...",
  "lifespan": "...",
  "anatomy": "...",
  "behaviour": "...",
  "reproduction": "...",
  "adaptations": "...",
  "ecology": "..."
}}

For an ANIMAL:
- diet_or_growth = what it eats
- include behaviour, anatomy and reproduction

For a PLANT:
- diet_or_growth = how it grows and develops
- anatomy = roots, stem, leaves, flowers, fruit/seeds where applicable
- behaviour = plant responses where scientifically meaningful
- reproduction = sexual/asexual reproduction
- adaptations = environmental adaptations

Keep each field concise but informative.
Return JSON only.
"""

    try:

        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
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

    except Exception as e:

        return {
            "error": str(e)
        }


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
            "Species information could not be found."
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

    # Determine animal/plant
    if ai_result:

        organism_type = (
            ai_result.get(
                "type",
                ""
            ).lower()
        )

    else:

        if major_group.lower() == "plantae":
            organism_type = "plant"

        elif major_group.lower() == "animalia":
            organism_type = "animal"

        else:
            organism_type = "organism"

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    if organism_type == "plant":

        st.title(
            f"🌱 {common_name}"
        )

    else:

        st.title(
            f"🐾 {common_name}"
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
            f"**Taxonomic rank:** {rank}"
        )

        st.write(
            f"**Major group:** {major_group}"
        )

    with col2:

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

    default_photo = taxon.get(
        "default_photo"
    )

    if default_photo:

        photo_url = get_large_photo_url(
            default_photo
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
    # BASIC AI INFORMATION
    # -----------------------------------------------------

    if ai_result:

        reason = ai_result.get(
            "reason",
            ""
        )

        confidence = ai_result.get(
            "confidence",
            None
        )

        if confidence is not None:

            st.write(
                f"**Identification confidence:** "
                f"{confidence}%"
            )

        if reason:

            st.write(
                f"**Identification reason:** "
                f"{reason}"
            )

    # -----------------------------------------------------
    # MORE INFORMATION BUTTON
    # -----------------------------------------------------

    st.divider()

    st.subheader(
        "🔬 More Information"
    )

    st.write(
        "Open this section if you want a deeper "
        "educational explanation."
    )

    if st.button(
        "🔬 Show More Information",
        type="primary",
        use_container_width=True,
        key="more_info_button"
    ):

        with st.spinner(
            "Preparing detailed information..."
        ):

            information = (
                generate_species_information(
                    common_name,
                    scientific_name,
                    organism_type
                )
            )

        st.session_state.species_info = (
            information
        )

        st.session_state.species_info_loaded = (
            True
        )

        st.rerun()

    # -----------------------------------------------------
    # DETAILED INFORMATION
    # -----------------------------------------------------

    if st.session_state.species_info_loaded:

        information = (
            st.session_state.species_info
        )

        if information.get("error"):

            st.error(
                "Detailed information could not "
                "be generated right now."
            )

        else:

            st.info(
                "The following detailed educational "
                "text is AI-generated and should be "
                "treated as an educational summary."
            )

            # REGION
            with st.expander(
                "🌍 Region & Distribution",
                expanded=True
            ):

                st.write(
                    information.get(
                        "region",
                        "Information unavailable."
                    )
                )

            # HABITAT
            with st.expander(
                "🌳 Habitat",
                expanded=True
            ):

                st.write(
                    information.get(
                        "habitat",
                        "Information unavailable."
                    )
                )

            # DIET / GROWTH
            if organism_type == "plant":

                title = "🌱 Growth & Development"

            else:

                title = "🍖 Diet & Feeding"

            with st.expander(
                title,
                expanded=True
            ):

                st.write(
                    information.get(
                        "diet_or_growth",
                        "Information unavailable."
                    )
                )

            # SIZE
            with st.expander(
                "📏 Size",
                expanded=False
            ):

                st.write(
                    information.get(
                        "size",
                        "Information unavailable."
                    )
                )

            # LIFESPAN
            with st.expander(
                "❤️ Lifespan",
                expanded=False
            ):

                st.write(
                    information.get(
                        "lifespan",
                        "Information unavailable."
                    )
                )

            # ANATOMY
            with st.expander(
                "🧬 Anatomy",
                expanded=False
            ):

                st.write(
                    information.get(
                        "anatomy",
                        "Information unavailable."
                    )
                )

            # BEHAVIOUR
            with st.expander(
                "🧠 Behaviour",
                expanded=False
            ):

                st.write(
                    information.get(
                        "behaviour",
                        "Information unavailable."
                    )
                )

            # REPRODUCTION
            with st.expander(
                "❤️ Reproduction",
                expanded=False
            ):

                st.write(
                    information.get(
                        "reproduction",
                        "Information unavailable."
                    )
                )

            # ADAPTATIONS
            with st.expander(
                "🌍 Adaptations",
                expanded=False
            ):

                st.write(
                    information.get(
                        "adaptations",
                        "Information unavailable."
                    )
                )

            # ECOLOGY
            with st.expander(
                "🌿 Ecological Role",
                expanded=False
            ):

                st.write(
                    information.get(
                        "ecology",
                        "Information unavailable."
                    )
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

    # -----------------------------------------------------
    # iNATURALIST SOURCE
    # -----------------------------------------------------

    taxon_id = taxon.get("id")

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
        "Identify animals and plants from photographs "
        "or search for species directly."
    )

    st.divider()

    # -----------------------------------------------------
    # Get example animal image
    # -----------------------------------------------------

    if (
        st.session_state.home_animal_image
        is None
    ):

        animal_taxon = (
            search_taxon_cached(
                "tiger"
            )
        )

        if (
            animal_taxon
            and not animal_taxon.get("error")
        ):

            st.session_state.home_animal_image = (
                get_large_photo_url(
                    animal_taxon.get(
                        "default_photo"
                    )
                )
            )

    # -----------------------------------------------------
    # Get example plant image
    # -----------------------------------------------------

    if (
        st.session_state.home_plant_image
        is None
    ):

        plant_taxon = (
            search_taxon_cached(
                "sunflower"
            )
        )

        if (
            plant_taxon
            and not plant_taxon.get("error")
        ):

            st.session_state.home_plant_image = (
                get_large_photo_url(
                    plant_taxon.get(
                        "default_photo"
                    )
                )
            )

    # -----------------------------------------------------
    # THREE MAIN OPTIONS
    # -----------------------------------------------------

    col1, col2, col3 = st.columns(
        3,
        gap="large"
    )

    # =====================================================
    # ANIMALS
    # =====================================================

    with col1:

        with st.container(border=True):

            if st.session_state.home_animal_image:

                st.image(
                    st.session_state.home_animal_image,
                    use_container_width=True
                )

            else:

                st.write("🐾")

            st.subheader(
                "🐾 Animals"
            )

            st.write(
                "Explore animals, habitats, "
                "behaviour, anatomy and more."
            )

            if st.button(
                "Explore Animals",
                use_container_width=True,
                key="animals_button"
            ):

                st.session_state.page = (
                    "search"
                )

                st.session_state.search_name = ""

                st.rerun()

    # =====================================================
    # PLANTS
    # =====================================================

    with col2:

        with st.container(border=True):

            if st.session_state.home_plant_image:

                st.image(
                    st.session_state.home_plant_image,
                    use_container_width=True
                )

            else:

                st.write("🌱")

            st.subheader(
                "🌱 Plants"
            )

            st.write(
                "Explore plants, growth, structure, "
                "reproduction and ecology."
            )

            if st.button(
                "Explore Plants",
                use_container_width=True,
                key="plants_button"
            ):

                st.session_state.page = (
                    "search"
                )

                st.session_state.search_name = ""

                st.rerun()

    # =====================================================
    # PHOTO IDENTIFICATION
    # =====================================================

    with col3:

        with st.container(border=True):

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
        "🌿 Biodiversity data and photographs "
        "are retrieved from iNaturalist."
    )


# =========================================================
# SEARCH PAGE
# =========================================================

def show_search():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        "🔎 Explore Nature"
    )

    st.write(
        "Search for an animal or plant by name."
    )

    search_name = st.text_input(
        "Search",
        value=st.session_state.search_name,
        placeholder=(
            "Example: Tiger, Rabbit, Mango, Neem..."
        )
    )

    if st.button(
        "🔎 Search",
        type="primary",
        use_container_width=True
    ):

        if not search_name.strip():

            st.warning(
                "Please enter a name."
            )

            return

        st.session_state.search_name = (
            search_name.strip()
        )

        with st.spinner(
            "Finding this species..."
        ):

            taxon = (
                search_taxon_cached(
                    search_name.strip()
                )
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

                # Reset detailed information
                st.session_state.species_info = None

                st.session_state.species_info_loaded = (
                    False
                )

                st.session_state.selected_taxon = (
                    taxon
                )

                st.session_state.selected_observations = (
                    observations
                )

                st.rerun()

            elif taxon and taxon.get(
                "error"
            ):

                st.error(
                    "iNaturalist error: "
                    + str(taxon["error"])
                )

            else:

                st.warning(
                    "No matching species was found."
                )

    # Show selected species
    if st.session_state.selected_taxon:

        show_species_page(
            st.session_state.selected_taxon,
            st.session_state.selected_observations
        )


# =========================================================
# IDENTIFICATION PAGE
# =========================================================

def show_identify():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        "📷 Identify an Animal or Plant"
    )

    st.write(
        "Upload a photograph and AI will try "
        "to identify the living organism."
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

            st.session_state.ai_result = None
            st.session_state.ai_model_used = None

            st.session_state.selected_taxon = None
            st.session_state.selected_observations = []

            st.session_state.species_info = None
            st.session_state.species_info_loaded = False
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

        if st.session_state.ai_result is None:

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
                        "The AI service is temporarily "
                        "unavailable."
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
        # SHOW AI RESULT
        # -------------------------------------------------

        if st.session_state.ai_result:

            result = (
                st.session_state.ai_result
            )

            organism_type = result.get(
                "type",
                "organism"
            )

            common_name = result.get(
                "common_name",
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

            if organism_type.lower() == "plant":

                st.success(
                    f"🌱 Identified: **{common_name}**"
                )

            else:

                st.success(
                    f"🐾 Identified: **{common_name}**"
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
                    + st.session_state.ai_model_used
                )

            # -------------------------------------------------
            # FIND iNATURALIST SPECIES
            # -------------------------------------------------

            if st.session_state.selected_taxon is None:

                if st.button(
                    "🌍 Find Species Information",
                    type="primary",
                    use_container_width=True
                ):

                    with st.spinner(
                        "Finding biodiversity information..."
                    ):

                        # Prefer scientific name
                        # when available
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

                            st.session_state.selected_taxon = (
                                taxon
                            )

                            st.session_state.selected_observations = (
                                observations
                            )

                            st.session_state.species_info = None

                            st.session_state.species_info_loaded = (
                                False
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

            if st.session_state.selected_taxon:

                show_species_page(
                    st.session_state.selected_taxon,
                    st.session_state.selected_observations,
                    ai_result=result
                )

    else:

        st.info(
            "📷 Upload a photograph to begin."
        )


# =========================================================
# APP ROUTER
# =========================================================

if st.session_state.page == "home":

    show_home()

elif st.session_state.page == "search":

    show_search()

elif st.session_state.page == "identify":

    show_identify()
