import streamlit as st
from sklearn.ensemble import RandomForestClassifier

st.title("🐾 Animal Encyclopedia & Predictor")
st.write("Explore animals or identify an unknown animal using measurements!")

# -----------------------------
# ANIMAL INFORMATION
# -----------------------------

animals = {

    "Dog": {
        "emoji": "🐶",
        "appearance": "Dogs have four legs, paws, a tail, fur, and many different body shapes.",
        "colour": "Black, white, brown, golden, grey and many mixed patterns.",
        "body": "Four legs with paws, a flexible spine, tail, ears and a strong sense of smell.",
        "region": "Domestic dogs are found almost everywhere in the world.",
        "habitat": "Human homes, farms, towns and cities.",
        "diet": "Omnivorous.",
        "size": "Highly variable depending on breed.",
        "weight": "Roughly 1.5–90+ kg depending on breed.",
        "lifespan": "Often around 10–13 years.",
        "fact": "Dogs have an exceptionally strong sense of smell."
    },

    "Cat": {
        "emoji": "🐱",
        "appearance": "Cats have a compact body, four legs, paws, a tail, whiskers and retractable claws.",
        "colour": "White, black, orange, grey, brown and many combinations.",
        "body": "Four legs, padded paws, flexible spine, tail, whiskers and sharp claws.",
        "region": "Domestic cats are found throughout the world.",
        "habitat": "Homes, farms, towns and cities.",
        "diet": "Carnivorous.",
        "size": "Usually around 45–50 cm long, excluding the tail.",
        "weight": "Often around 3–6 kg.",
        "lifespan": "Around 12–18 years.",
        "fact": "Cats can rotate their ears to help locate sounds."
    },

    "Lion": {
        "emoji": "🦁",
        "appearance": "Lions have muscular bodies, four legs, a long tail and a large head.",
        "colour": "Usually tan, golden or brownish.",
        "body": "Four powerful legs, paws, claws, large teeth and a long tail.",
        "region": "Mainly sub-Saharan Africa, with a small wild population in India.",
        "habitat": "Grasslands, savannas and open woodland.",
        "diet": "Carnivorous.",
        "size": "Large cat; males are generally larger than females.",
        "weight": "Often around 120–250 kg.",
        "lifespan": "Around 10–15 years in the wild.",
        "fact": "Lions normally live in social groups called prides."
    },

    "Tiger": {
        "emoji": "🐯",
        "appearance": "Tigers have a large muscular body, four legs, a long tail and a striped coat.",
        "colour": "Orange or reddish-orange with dark stripes.",
        "body": "Four powerful legs, large paws, claws, strong jaws and a long tail.",
        "region": "Parts of Asia, including India, Russia and Southeast Asia.",
        "habitat": "Forests, grasslands and wetlands.",
        "diet": "Carnivorous.",
        "size": "The largest living cat species.",
        "weight": "Often around 70–300 kg.",
        "lifespan": "Around 10–15 years in the wild.",
        "fact": "Every tiger has a unique stripe pattern."
    },

    "Elephant": {
        "emoji": "🐘",
        "appearance": "Elephants have huge bodies, large ears, four legs and a long trunk.",
        "colour": "Usually grey to grey-brown.",
        "body": "Four thick legs, a trunk, large ears, tusks in many individuals and a short tail.",
        "region": "Africa and parts of Asia.",
        "habitat": "Savannas, forests, grasslands and wetlands.",
        "diet": "Herbivorous.",
        "size": "The largest living land animals.",
        "weight": "Can weigh several thousand kilograms.",
        "lifespan": "Often around 60–70 years.",
        "fact": "An elephant's trunk is used for breathing, smelling, touching, drinking and grabbing food."
    },

    "Horse": {
        "emoji": "🐴",
        "appearance": "Horses have a large body, four long legs, hooves, a mane and a tail.",
        "colour": "Black, brown, chestnut, grey, white and many patterns.",
        "body": "Four legs ending in hooves, a mane along the neck and a long tail.",
        "region": "Domestic horses are found worldwide.",
        "habitat": "Grasslands, farms and plains.",
        "diet": "Herbivorous.",
        "size": "Varies greatly among breeds.",
        "weight": "Often around 400–600 kg.",
        "lifespan": "Often around 25–30 years.",
        "fact": "Horses can sleep both standing up and lying down."
    },

    "Giraffe": {
        "emoji": "🦒",
        "appearance": "Giraffes have extremely long necks and legs and a sloping back.",
        "colour": "Light brown or tan with darker patches.",
        "body": "Four very long legs, a long neck, small horns called ossicones and a long tail.",
        "region": "Sub-Saharan Africa.",
        "habitat": "Savannas, grasslands and open woodlands.",
        "diet": "Herbivorous; mainly leaves.",
        "size": "The tallest living land animals.",
        "weight": "Often around 800–1,200 kg.",
        "lifespan": "Around 20–25 years in the wild.",
        "fact": "Giraffes can reach vegetation high above the ground."
    },

    "Panda": {
        "emoji": "🐼",
        "appearance": "Giant pandas have a round body, black-and-white fur, four legs and a short tail.",
        "colour": "Distinctive black-and-white coat.",
        "body": "Four legs, large paws, strong jaws and teeth adapted for crushing bamboo.",
        "region": "Mountainous areas of central China.",
        "habitat": "Temperate mountain forests with bamboo.",
        "diet": "Mostly bamboo.",
        "size": "About 1.2–1.9 metres long.",
        "weight": "Adults commonly weigh around 70–120 kg.",
        "lifespan": "Around 15–20 years in the wild.",
        "fact": "Pandas have a specialized wrist bone that helps them hold bamboo."
    },

    "Monkey": {
        "emoji": "🐒",
        "appearance": "Monkeys have four limbs, a head, torso and often a tail.",
        "colour": "Extremely variable depending on species.",
        "body": "Four limbs, grasping hands and feet, and often a tail.",
        "region": "Africa, Asia, Central America and South America depending on species.",
        "habitat": "Forests, woodlands and grasslands.",
        "diet": "Often omnivorous.",
        "size": "Ranges from very small to much larger monkeys.",
        "weight": "Highly variable by species.",
        "lifespan": "Varies greatly by species.",
        "fact": "Monkeys are highly diverse, with many different species."
    },

    "Zebra": {
        "emoji": "🦓",
        "appearance": "Zebras have horse-like bodies, four legs, hooves, upright manes and stripes.",
        "colour": "Black-and-white striped coat.",
        "body": "Four legs ending in hooves, a mane, tail and strong teeth.",
        "region": "Eastern and southern Africa.",
        "habitat": "Grasslands, savannas and some woodland areas.",
        "diet": "Herbivorous; mainly grasses.",
        "size": "Medium-to-large hoofed mammals.",
        "weight": "Often around 175–450 kg.",
        "lifespan": "Often around 20–25 years in the wild.",
        "fact": "Each zebra has a unique pattern of stripes."
    }
}

# -----------------------------
# MACHINE LEARNING MODEL
# -----------------------------

features = [
    [40,70,10,4], [50,80,20,4], [60,100,30,4],
    [20,40,3,4], [25,45,4,4], [30,50,6,4],
    [100,180,150,4], [120,200,190,4], [130,220,220,4],
    [90,180,120,4], [100,200,180,4], [110,220,230,4],
    [250,400,3000,4], [300,500,5000,4], [350,600,6000,4],
    [140,220,400,4], [160,250,500,4], [170,270,600,4],
    [400,280,800,4], [500,300,1000,4], [550,350,1200,4],
    [60,120,70,4], [70,150,100,4], [80,170,120,4],
    [40,60,8,4], [60,80,15,4], [80,100,25,4],
    [120,200,250,4], [130,230,350,4], [150,250,400,4]
]

labels = [
    "Dog","Dog","Dog",
    "Cat","Cat","Cat",
    "Lion","Lion","Lion",
    "Tiger","Tiger","Tiger",
    "Elephant","Elephant","Elephant",
    "Horse","Horse","Horse",
    "Giraffe","Giraffe","Giraffe",
    "Panda","Panda","Panda",
    "Monkey","Monkey","Monkey",
    "Zebra","Zebra","Zebra"
]

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(features, labels)

# -----------------------------
# APP OPTIONS
# -----------------------------

option = st.radio(
    "What would you like to do?",
    ["📚 Explore Animal", "🤖 Identify Unknown Animal"]
)

# -----------------------------
# EXPLORE ANIMAL
# -----------------------------

if option == "📚 Explore Animal":

    animal = st.selectbox(
        "Which animal do you want to learn about?",
        list(animals.keys())
    )

    if st.button("🔍 Explore Animal"):

        info = animals[animal]

        if animal == "Panda":
            st.image(
                "https://commons.wikimedia.org/wiki/Special:FilePath/Giant%20panda%20animal.jpg",
                caption="Giant Panda"
            )

        st.header(info["emoji"] + " " + animal)

        st.subheader("👀 Appearance")
        st.write(info["appearance"])

        st.subheader("🎨 Colour")
        st.write(info["colour"])

        st.subheader("🦴 Body & Legs")
        st.write(info["body"])

        st.subheader("📏 Size")
        st.write(info["size"])

        st.subheader("⚖️ Weight")
        st.write(info["weight"])

        st.subheader("🌍 Region")
        st.write(info["region"])

        st.subheader("🌿 Habitat")
        st.write(info["habitat"])

        st.subheader("🍃 Diet")
        st.write(info["diet"])

        st.subheader("⏳ Lifespan")
        st.write(info["lifespan"])

        st.subheader("💡 Interesting Fact")
        st.write(info["fact"])

# -----------------------------
# IDENTIFY UNKNOWN ANIMAL
# -----------------------------

else:

    st.header("🤖 Identify an Unknown Animal")

    st.write("Enter the animal's approximate measurements.")

    height = st.number_input(
        "📏 Height (cm)",
        min_value=1.0,
        value=70.0
    )

    length = st.number_input(
        "📐 Body Length (cm)",
        min_value=1.0,
        value=150.0
    )

    weight = st.number_input(
        "⚖️ Weight (kg)",
        min_value=0.1,
        value=100.0
    )

    legs = st.number_input(
        "🦵 Number of Legs",
        min_value=0,
        max_value=8,
        value=4,
        step=1
    )

    if st.button("🔍 Predict Animal"):

        prediction = model.predict(
            [[height, length, weight, legs]]
        )

        predicted_animal = prediction[0]

        st.success(
            "🐾 Predicted Animal: " + predicted_animal
        )

        info = animals[predicted_animal]

        st.header(
            info["emoji"] + " " + predicted_animal
        )

        st.subheader("👀 Appearance")
        st.write(info["appearance"])

        st.subheader("🎨 Colour")
        st.write(info["colour"])

        st.subheader("🦴 Body & Legs")
        st.write(info["body"])

        st.subheader("📏 Size")
        st.write(info["size"])

        st.subheader("⚖️ Weight")
        st.write(info["weight"])

        st.subheader("🌍 Region")
        st.write(info["region"])

        st.subheader("🌿 Habitat")
        st.write(info["habitat"])

        st.subheader("🍃 Diet")
        st.write(info["diet"])

        st.subheader("⏳ Lifespan")
        st.write(info["lifespan"])

        st.subheader("💡 Interesting Fact")
        st.write(info["fact"])
