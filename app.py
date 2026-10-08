import streamlit as st
import requests
import hashlib
import json
import time
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
    "image_bytes": None,
    "image_hash": None,
    "ai_result": None,
    "ai_model_used": None,
    "selected_taxon": None,
    "selected_observations": [],
    "search_name": "",
    "home_nature_image": None
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
            search_name.strip().lower()
        )

        # Exact common/scientific name
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

        # Otherwise use first result
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
# LARGE PHOTO URL
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

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash"
]


# =========================================================
# GEMINI IMAGE IDENTIFICATION
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

Focus mainly on animals and plants.

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

    # Find JSON inside response
    if not text.startswith("{"):

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            text = text[start:end + 1]

    return json.loads(text)


# =========================================================
# GEMINI IDENTIFICATION
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
            "error": (
                "GEMINI_API_KEY is missing "
                "or invalid."
            ),
            "model": None
        }

    errors = []

    for model_name in GEMINI_MODELS:

        for attempt in range(2):

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
                    f"{model_name} "
                    f"attempt {attempt + 1}: "
                    f"{str(e)}"
                )

                if attempt == 0:
                    time.sleep(2)

    return {
        "success": False,
        "error": "\n\n".join(errors),
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
        taxon.get("iconic_taxon_name")
        or "Unknown"
    )

    organism_type = determine_organism_type(
        taxon,
        ai_result
    )

    # =====================================================
    # HEADER
    # =====================================================

    if organism_type == "plant":

        st.title(
            "🌱 " + common_name
        )

    elif organism_type == "animal":

        st.title(
            "🐾 " + common_name
        )

    else:

        st.title(
            "🌍 " + common_name
        )

    st.markdown(
        "### *" + scientific_name + "*"
    )

    # =====================================================
    # BASIC INFORMATION
    # =====================================================

    st.subheader(
        "📚 Basic Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "**Scientific name:** *"
            + scientific_name
            + "*"
        )

        st.write(
            "**Taxonomic rank:** "
            + rank
        )

    with col2:

        st.write(
            "**Major group:** "
            + major_group
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

    # =====================================================
    # MAIN PHOTO
    # =====================================================

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

    # =====================================================
    # AI DETAILS
    # =====================================================

    if ai_result:

        confidence = ai_result.get(
            "confidence"
        )

        if confidence is not None:

            st.write(
                "**Identification confidence:** "
                + str(confidence)
                + "%"
            )

        reason = ai_result.get(
            "reason",
            ""
        )

        if reason:

            st.write(
                "**Identification reason:** "
                + str(reason)
            )

    # =====================================================
    # MORE INFORMATION
    # =====================================================

    st.divider()

    st.subheader(
        "🔬 More Information"
    )

    taxon_id = taxon.get("id")

    if taxon_id:

        inat_url = (
            "https://www.inaturalist.org/taxa/"
            + str(taxon_id)
        )

        st.link_button(
            "🌿 Explore on iNaturalist",
            inat_url,
            use_container_width=True
        )

    # =====================================================
    # MORE PHOTOS
    # =====================================================

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


# =========================================================
# HOME PAGE
# =========================================================

def show_home():

    st.title(
        "🌍 Nature Encyclopedia AI"
    )

    st.subheader(
        "Explore the living world"
    )

    st.write(
        "Search for animals and plants, "
        "or identify one from a photograph."
    )

    st.divider()

    # =====================================================
    # HOME IMAGE
    # =====================================================

    if (
        st.session_state.home_nature_image
        is None
    ):

        example_taxon = (
            search_taxon_cached("tiger")
        )

        if (
            example_taxon
            and not example_taxon.get("error")
        ):

            st.session_state.home_nature_image = (
                get_large_photo_url(
                    example_taxon.get(
                        "default_photo"
                    )
                )
            )

    # =====================================================
    # TWO OPTIONS
    # =====================================================

    col1, col2 = st.columns(
        2,
        gap="large"
    )

    # =====================================================
    # EXPLORE FLORA & FAUNA
    # =====================================================

    with col1:

        with st.container(
            border=True
        ):

            if st.session_state.home_nature_image:

                st.image(
                    st.session_state.home_nature_image,
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
                "Search animals and plants "
                "in one place."
            )

            if st.button(
                "Explore Flora & Fauna",
                type="primary",
                use_container_width=True,
                key="explore_nature_button"
            ):

                st.session_state.page = "search"

                st.session_state.search_name = ""

                st.session_state.selected_taxon = None

                st.session_state.selected_observations = []

                st.rerun()

    # =====================================================
    # IDENTIFY FROM PHOTO
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
                "Upload a photograph and let "
                "AI identify an animal or plant."
            )

            if st.button(
                "Identify from Photo",
                type="primary",
                use_container_width=True,
                key="photo_button"
            ):

                st.session_state.page = "identify"

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
        "🌿 Explore Flora & Fauna"
    )

    st.write(
        "Search for an animal or plant "
        "by common or scientific name."
    )

    # =====================================================
    # SEARCH FORM
    # =====================================================

    with st.form(
        "nature_search_form"
    ):

        search_name = st.text_input(
            "Search organism",
            value=st.session_state.search_name,
            placeholder=(
                "Example: Tiger, Rabbit, "
                "Mango, Neem..."
            )
        )

        submitted = st.form_submit_button(
            "🔎 Search",
            use_container_width=True
        )

    # =====================================================
    # SEARCH
    # =====================================================

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

            taxon = search_taxon_cached(
                search_name.strip()
            )

            if (
                taxon
                and not taxon.get("error")
            ):

                taxon_id = taxon.get("id")

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

                st.rerun()

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
                    "No matching organism was found."
                )

    # =====================================================
    # SHOW SPECIES
    # =====================================================

    if st.session_state.selected_taxon:

        show_species_page(
            st.session_state.selected_taxon,
            st.session_state.selected_observations
        )


# =========================================================
# PHOTO IDENTIFICATION PAGE
# =========================================================

def show_identify():

    if st.button("← Home"):

        st.session_state.page = "home"

        st.rerun()

    st.title(
        "📷 Identify an Animal or Plant"
    )

    st.write(
        "Upload a photograph and AI will "
        "try to identify the organism."
    )

    # =====================================================
    # UPLOAD
    # =====================================================

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

        image_bytes = uploaded_file.getvalue()

        image_hash = hashlib.sha256(
            image_bytes
        ).hexdigest()

        # =================================================
        # NEW IMAGE
        # =================================================

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

    # =====================================================
    # DISPLAY IMAGE
    # =====================================================

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

        # =================================================
        # IDENTIFY
        # =================================================

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
                        "The AI service is "
                        "temporarily unavailable."
                    )

                    with st.expander(
                        "Technical details"
                    ):

                        st.code(
                            result["error"]
                        )

        # =================================================
        # AI RESULT
        # =================================================

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
                    "🌱 Identified: **"
                    + common_name
                    + "**"
                )

            else:

                st.success(
                    "🐾 Identified: **"
                    + common_name
                    + "**"
                )

            st.metric(
                "AI Confidence",
                str(confidence) + "%"
            )

            if scientific_name:

                st.write(
                    "**Scientific name:** *"
                    + scientific_name
                    + "*"
                )

            if reason:

                st.write(
                    "**Why:** "
                    + reason
                )

            if st.session_state.ai_model_used:

                st.caption(
                    "AI model: "
                    + st.session_state.ai_model_used
                )

            # =============================================
            # FIND iNATURALIST SPECIES
            # =============================================

            if (
                st.session_state.selected_taxon
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
                            and not taxon.get("error")
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

                            st.rerun()

                        else:

                            st.warning(
                                "The organism was identified, "
                                "but no matching iNaturalist "
                                "taxon was found."
                            )

            # =============================================
            # SPECIES PAGE
            # =============================================

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
    # =========================================================
# 🌿 NATURE ENCYCLOPEDIA AI — GOGY & TITLI VOICE LAYER
# =========================================================

import streamlit.components.v1 as components
from google.genai import types
import html


# =========================================================
# VOICE SESSION STATE
# =========================================================

voice_defaults = {
    "voice_enabled": True,
    "gogy_welcomed": False,
    "last_voice_question": "",
    "voice_transcript": "",
}

for key, value in voice_defaults.items():

    if key not in st.session_state:

        st.session_state[key] = value


# =========================================================
# GEMINI — UNDERSTAND MICROPHONE QUESTION
# =========================================================

def understand_voice_question(audio_bytes):

    if gemini_client is None:

        return None

    try:

        prompt = """
Listen to this user's voice recording.

Your job is ONLY to understand what the user is asking.

Return ONLY the user's question as plain text.

Do not answer the question.
Do not add explanations.
Do not use quotation marks.

Examples:

User says:
"Tell me about tigers"

Return:
Tell me about tigers

User says:
"What is a butterfly?"

Return:
What is a butterfly?

User says:
"Show me information about neem"

Return:
Show me information about neem
"""

        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type="audio/wav"
        )

        response = gemini_client.models.generate_content(

            model=GEMINI_MODELS[0],

            contents=[
                prompt,
                audio_part
            ]
        )

        text = (
            response.text
            or ""
        ).strip()

        return text if text else None

    except Exception:

        return None


# =========================================================
# GOGY — CHARACTER INTRO
# =========================================================

def show_gogy_home():

    st.markdown(
        """
        <style>

        .gogy-box {

            border-radius: 28px;
            padding: 22px;
            margin-top: 10px;
            margin-bottom: 20px;

            background:
                linear-gradient(
                    135deg,
                    rgba(220,245,255,0.95),
                    rgba(245,250,255,0.95)
                );

            border: 2px solid rgba(100,180,220,0.35);

            box-shadow:
                0 10px 35px
                rgba(0,0,0,0.08);

        }

        .gogy-character {

            font-size: 70px;

            display: inline-block;

            animation:
                gogyFly 2.2s
                ease-in-out
                infinite;

        }

        @keyframes gogyFly {

            0% {
                transform:
                    translateY(0px)
                    rotate(-3deg);
            }

            50% {
                transform:
                    translateY(-12px)
                    rotate(3deg);
            }

            100% {
                transform:
                    translateY(0px)
                    rotate(-3deg);
            }

        }

        .gogy-title {

            font-size: 28px;
            font-weight: 800;

        }

        .gogy-text {

            font-size: 18px;

        }

        </style>

        <div class="gogy-box">

            <div class="gogy-character">
                🧒
            </div>

            <div class="gogy-title">
                Hi! I'm Gogy! 🌿
            </div>

            <div class="gogy-text">
                Hehe! What do you wanna know
                about the wonderful world of nature? 🌎
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# GOGY VOICE
# =========================================================

def gogy_voice():

    gogy_text = (
        "Hiii! I'm Gogy! "
        "Hehe! What do you wanna know "
        "about the wonderful world of nature?"
    )

    components.html(

        f"""
        <script>

        const text = {json.dumps(gogy_text)};

        function speakGogy() {{

            if (!window.speechSynthesis) return;

            window.speechSynthesis.cancel();

            const speech =
                new SpeechSynthesisUtterance(text);

            speech.rate = 0.92;
            speech.pitch = 1.45;
            speech.volume = 1.0;

            const voices =
                window.speechSynthesis.getVoices();

            const voice =
                voices.find(v =>
                    v.lang &&
                    v.lang.toLowerCase()
                    .startsWith("en")
                );

            if (voice) {{
                speech.voice = voice;
            }}

            window.speechSynthesis.speak(speech);
        }}

        setTimeout(
            speakGogy,
            500
        );

        </script>
        """,

        height=1
    )


# =========================================================
# GOGY USER CONTROLS
# =========================================================

def show_gogy_controls():

    st.markdown(
        "### 🧒 Talk to Gogy"
    )

    col1, col2 = st.columns(2)

    with col1:

        typed_question = st.text_input(
            "⌨️ Type to Gogy",
            placeholder=(
                "Example: Tell me about frogs..."
            ),
            key="gogy_text_question"
        )

    with col2:

        voice_question = st.audio_input(
            "🎤 Talk to Gogy",
            sample_rate=16000,
            key="gogy_microphone"
        )

    # =====================================================
    # TYPED QUESTION
    # =====================================================

    if typed_question:

        if st.button(
            "🧒 Ask Gogy",
            type="primary",
            use_container_width=True,
            key="gogy_ask_text"
        ):

            process_gogy_question(
                typed_question
            )

    # =====================================================
    # MICROPHONE QUESTION
    # =====================================================

    if voice_question:

        audio_bytes = voice_question.getvalue()

        with st.spinner(
            "🧒 Gogy is listening... 👂"
        ):

            transcript = (
                understand_voice_question(
                    audio_bytes
                )
            )

        if transcript:

            st.session_state.voice_transcript = (
                transcript
            )

            st.success(
                "🧒 Gogy heard: "
                + transcript
            )

            process_gogy_question(
                transcript
            )

        else:

            st.warning(
                "Gogy couldn't understand that."
                " Try speaking a little more clearly."
            )


# =========================================================
# GOGY QUESTION PROCESSOR
# =========================================================

def process_gogy_question(question):

    question = (
        str(question)
        .strip()
    )

    if not question:

        return

    with st.spinner(
        "🧒 Gogy is looking through nature..."
    ):

        taxon = search_taxon_cached(
            question
        )

        # -------------------------------------------------
        # If direct search failed, ask Gemini
        # to extract the organism name.
        # -------------------------------------------------

        if (
            taxon is None
            or taxon.get("error")
        ):

            if gemini_client:

                try:

                    prompt = f"""
From the following user question,
extract the name of the animal or plant
the user wants information about.

User question:
{question}

Return ONLY the organism name.

If no organism can be identified,
return:
UNKNOWN
"""

                    response = (
                        gemini_client
                        .models
                        .generate_content(
                            model=GEMINI_MODELS[0],
                            contents=prompt
                        )
                    )

                    organism_name = (
                        response.text
                        .strip()
                    )

                    if (
                        organism_name
                        and organism_name.upper()
                        != "UNKNOWN"
                    ):

                        taxon = (
                            search_taxon_cached(
                                organism_name
                            )
                        )

                except Exception:

                    pass

        # -------------------------------------------------
        # FOUND
        # -------------------------------------------------

        if (
            taxon
            and not taxon.get("error")
        ):

            taxon_id = taxon.get("id")

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

            st.session_state.search_name = (
                taxon.get(
                    "preferred_common_name"
                )
                or taxon.get("name")
                or question
            )

            st.session_state.page = "search"

            st.rerun()

        else:

            st.warning(
                "Awww... Gogy couldn't find "
                "that organism yet. Try another name! 🥺"
            )


# =========================================================
# TITLI — SPECIES AUDIO READER
# =========================================================

def show_titli_reader(taxon):

    if not taxon:
        return

    common_name = (
        taxon.get(
            "preferred_common_name"
        )
        or taxon.get("name")
        or "this organism"
    )

    scientific_name = (
        taxon.get("name")
        or ""
    )

    major_group = (
        taxon.get(
            "iconic_taxon_name"
        )
        or ""
    )

    # -----------------------------------------------------
    # INFORMATION TEXT
    # -----------------------------------------------------

    reading_text = f"""
Hello! I'm Titli! 🦋

Ooooh! Today we're learning about
{common_name}!

Its scientific name is
{scientific_name}.

It belongs to the group
{major_group}.

Isn't nature amazing?

Hehe! If you want to know more,
keep exploring with me!
"""

    # -----------------------------------------------------
    # CHARACTER CARD
    # -----------------------------------------------------

    st.markdown(
        f"""
        <style>

        .titli-box {{

            border-radius: 28px;

            padding: 20px;

            margin-top: 25px;

            background:
                linear-gradient(
                    135deg,
                    rgba(255,235,248,0.95),
                    rgba(255,250,252,0.95)
                );

            border:
                2px solid
                rgba(230,130,190,0.30);

            box-shadow:
                0 10px 35px
                rgba(0,0,0,0.08);

        }}

        .titli-character {{

            font-size: 68px;

            display: inline-block;

            animation:
                titliFly 2s
                ease-in-out
                infinite;

        }}

        @keyframes titliFly {{

            0% {{
                transform:
                    translateY(0px)
                    rotate(-4deg);
            }}

            50% {{
                transform:
                    translateY(-13px)
                    rotate(4deg);
            }}

            100% {{
                transform:
                    translateY(0px)
                    rotate(-4deg);
            }}

        }}

        .titli-title {{

            font-size: 27px;
            font-weight: 800;

        }}

        </style>

        <div class="titli-box">

            <div class="titli-character">
                👧🦋
            </div>

            <div class="titli-title">
                Hiii! I'm Titli! 🌸
            </div>

            <p>
                Ooooh! You want me to read this
                for you? Hehe! 💕
            </p>

        </div>
        """,
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # READ / LISTEN CHOICE
    # -----------------------------------------------------

    st.markdown(
        "### 📖 How do you want to explore?"
    )

    choice = st.radio(
        "Choose",
        [
            "📖 I'll read it myself",
            "🦋🔊 Let Titli read it"
        ],
        horizontal=True,
        label_visibility="collapsed",
        key="titli_mode"
    )

    if choice == "📖 I'll read it myself":

        st.info(
            "📖 Perfect! Take your time "
            "and explore the information yourself."
        )

        return
# -----------------------------------------------------
    # TITLI READER
    # -----------------------------------------------------

    render_titli_audio_reader(
        reading_text
    )


# =========================================================
# TITLI AUDIO READER
# =========================================================

def render_titli_audio_reader(text):

    safe_text = html.escape(
        text
    )

    words = text.split()

    word_html = ""

    for index, word in enumerate(words):

        word_html += (
            f'<span class="word" '
            f'data-index="{index}">'
            f'{html.escape(word)}'
            f'</span> '
        )

    components.html(

        f"""
        <style>

        body {{
            font-family:
                Arial,
                sans-serif;

            background:
                transparent;

            margin: 0;
            padding: 0;
        }}

        .reader {{

            padding: 18px;

            border-radius: 22px;

            background:
                linear-gradient(
                    135deg,
                    #fff7fc,
                    #f5fbff
                );

            border:
                2px solid
                rgba(220,150,200,0.25);

        }}

        .reader-title {{

            font-size: 22px;
            font-weight: 800;

            margin-bottom: 12px;

        }}

        .reading-text {{

            font-size: 19px;

            line-height: 1.9;

        }}

        .word {{

            padding:
                2px 4px;

            border-radius:
                7px;

            transition:
                all 0.12s ease;

        }}

        .word.active {{

            background:
                #ffe58f;

            transform:
                scale(1.05);

            display:
                inline-block;

            box-shadow:
                0 2px 8px
                rgba(0,0,0,0.10);

        }}

        .butterfly {{

            display:
                inline-block;

            font-size:
                25px;

            margin-left:
                5px;

            animation:
                flutter 0.7s
                ease-in-out
                infinite alternate;

        }}

        @keyframes flutter {{

            from {{
                transform:
                    translateY(0px)
                    rotate(-8deg);
            }}

            to {{
                transform:
                    translateY(-5px)
                    rotate(8deg);
            }}

        }}

        button {{

            border: none;

            border-radius: 12px;

            padding:
                10px 15px;

            margin:
                4px;

            cursor: pointer;

            font-size: 15px;

        }}

        </style>

        <div class="reader">

            <div class="reader-title">
                🦋 Titli is ready!
            </div>

            <div
                id="readingText"
                class="reading-text"
            >
                {word_html}
                <span
                    id="butterfly"
                    class="butterfly"
                    style="display:none;"
                >
                    🦋
                </span>
            </div>

            <br>

            <button
                onclick="startReading()"
            >
                ▶️ Listen
            </button>

            <button
                onclick="pauseReading()"
            >
                ⏸️ Pause
            </button>

            <button
                onclick="resumeReading()"
            >
                ▶️ Resume
            </button>

            <button
                onclick="stopReading()"
            >
                ⏹️ Stop
            </button>

        </div>

        <script>

        const text =
            {json.dumps(text)};

        const words =
            Array.from(
                document.querySelectorAll(".word")
            );

        const butterfly =
            document.getElementById(
                "butterfly"
            );

        let speech = null;

        function clearWords() {{

            words.forEach(
                w =>
                    w.classList.remove(
                        "active"
                    )
            );

            butterfly.style.display =
                "none";
        }}

        function startReading() {{

            if (
                !window.speechSynthesis
            ) {{

                alert(
                    "Speech is not supported "
                    + "in this browser."
                );

                return;
            }}

            window.speechSynthesis.cancel();

            clearWords();

            speech =
                new SpeechSynthesisUtterance(
                    text
                );

            /*
             * Titli's personality:
             *
             * slightly youthful
             * sweet
             * playful
             * expressive
             */

            speech.rate =
                0.88;

            speech.pitch =
                1.48;

            speech.volume =
                1.0;

            const voices =
                window.speechSynthesis
                .getVoices();

            const femaleVoice =
                voices.find(
                    v =>
                        v.lang &&
                        v.lang
                            .toLowerCase()
                            .startsWith("en")
                );

            if (femaleVoice) {{
                speech.voice =
                    femaleVoice;
            }}

            speech.onboundary =
                function(event) {{

                    if (
                        event.name !==
                        "word"
                    ) {{
                        return;
                    }}

                    const characterIndex =
                        event.charIndex;

                    let currentIndex = 0;

                    for (
                        let i = 0;
                        i < words.length;
                        i++
                    ) {{

                        const word =
                            words[i]
                            .textContent;

                        const start =
                            currentIndex;

                        const end =
                            currentIndex
                            + word.length;

                        if (
                            characterIndex >= start
                            &&
                            characterIndex <= end
                        ) {{

                            words.forEach(
                                w =>
                                    w.classList
                                    .remove(
                                        "active"
                                    )
                            );

                            words[i]
                                .classList
                                .add(
                                    "active"
                                );

                            butterfly.style.display =
                                "inline-block";

                            words[i]
                                .after(
                                    butterfly
                                );

                            break;
                        }}

                        currentIndex =
                            end + 1;
                    }}
                }};

            speech.onend =
                function() {{

                    clearWords();

                }};

            window.speechSynthesis
                .speak(speech);

        }}

        function pauseReading() {{

            if (
                window.speechSynthesis
            ) {{

                window.speechSynthesis
                    .pause();

            }}

        }}

        function resumeReading() {{

            if (
                window.speechSynthesis
            ) {{

                window.speechSynthesis
                    .resume();

            }}

        }}

        function stopReading() {{

            if (
                window.speechSynthesis
            ) {{

                window.speechSynthesis
                    .cancel();

            }}

            clearWords();

        }}

        </script>
        """,

        height=430
    )


# =========================================================
# CHARACTER VOICE LAYER
# =========================================================

def show_character_layer():

    # =====================================================
    # HOME → GOGY
    # =====================================================

    if st.session_state.page == "home":

        show_gogy_home()

        if st.session_state.voice_enabled:

            if not st.session_state.gogy_welcomed:

                gogy_voice()

                st.session_state.gogy_welcomed = True

        show_gogy_controls()

    # =====================================================
    # SPECIES → TITLI
    # =====================================================

    if st.session_state.selected_taxon:

        show_titli_reader(
            st.session_state.selected_taxon
        )


# =========================================================
# RUN THE NEW VOICE LAYER
# =========================================================

show_character_layer()
