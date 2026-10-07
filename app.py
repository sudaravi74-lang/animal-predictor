 import streamlit as st

st.title("🐾 Animal Encyclopedia")
st.write("Choose an animal to explore its body, habitat, diet and more!")

animals = {

    "Dog": {
        "emoji": "🐶",
        "appearance": "Dogs have four legs, paws, a tail, fur, and many different body shapes.",
        "colour": "Black, white, brown, golden, grey and many mixed patterns.",
        "body": "Four legs with paws, a flexible spine, tail, ears and a strong sense of smell.",
        "region": "Domestic dogs are found almost everywhere in the world.",
        "habitat": "Human homes, farms, towns and cities.",
        "diet": "Omnivorous; dogs can eat both animal and plant-based foods.",
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
        "habitat": "Homes, farms, towns, cities and outdoor environments.",
        "diet": "Carnivorous; cats naturally depend heavily on animal-based food.",
        "size": "Usually around 45–50 cm long, excluding the tail.",
        "weight": "Often around 3–6 kg.",
        "lifespan": "Domestic cats commonly live around 12–18 years.",
        "fact": "Cats can rotate their ears to help locate sounds."
    },

    "Lion": {
        "emoji": "🦁",
        "appearance": "Lions have muscular bodies, four legs, a long tail and a large head.",
        "colour": "Usually tan, golden or brownish.",
        "body": "Four powerful legs, paws, claws, large teeth and a long tail. Adult males usually have a mane.",
        "region": "Mainly sub-Saharan Africa, with a small wild population in India.",
        "habitat": "Grasslands, savannas and open woodland.",
        "diet": "Carnivorous; mainly large and medium-sized mammals.",
        "size": "Large cat; males are generally larger than females.",
        "weight": "Often around 120–250 kg.",
        "lifespan": "Wild lions often live around 10–15 years.",
        "fact": "Lions normally live in social groups called prides."
    },

    "Tiger": {
        "emoji": "🐯",
        "appearance": "Tigers have a large muscular body, four legs, a long tail and a striped coat.",
        "colour": "Orange or reddish-orange with dark stripes.",
        "body": "Four powerful legs, large paws, claws, strong jaws and a long tail.",
        "region": "Parts of Asia, including India, Russia and Southeast Asia.",
        "habitat": "Forests, grasslands, wetlands and other suitable habitats.",
        "diet": "Carnivorous; mainly deer, wild pigs and other mammals.",
        "size": "The largest living cat species.",
        "weight": "Often around 70–300 kg depending on sex and subspecies.",
        "lifespan": "Wild tigers often live around 10–15 years.",
        "fact": "Every tiger has a unique stripe pattern."
    },

    "Elephant": {
        "emoji": "🐘",
        "appearance": "Elephants have huge bodies, large ears, four legs and a long trunk.",
        "colour": "Usually grey to grey-brown.",
        "body": "Four thick legs, a trunk, large ears, tusks in many individuals and a short tail.",
        "region": "Africa and parts of Asia.",
        "habitat": "Savannas, forests, grasslands and wetlands.",
        "diet": "Herbivorous; grasses, leaves, bark, roots and other vegetation.",
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
        "habitat": "Grasslands, farms, plains and human-managed environments.",
        "diet": "Herbivorous; mainly grasses and other plant material.",
        "size": "Varies greatly among breeds.",
        "weight": "Often around 400–600 kg.",
        "lifespan": "Often around 25–30 years.",
        "fact": "Horses can sleep both standing up and lying down."
    },

    "Giraffe": {
        "emoji": "🦒",
        "appearance": "Giraffes have extremely long necks and legs, a sloping back and a long tongue.",
        "colour": "Light brown or tan with darker irregular patches.",
        "body": "Four very long legs, a long neck, small horns called ossicones and a long tail.",
        "region": "Sub-Saharan Africa.",
        "habitat": "Savannas, grasslands and open woodlands.",
        "diet": "Herbivorous; mainly leaves from trees and shrubs.",
        "size": "The tallest living land animals.",
        "weight": "Often around 800–1,200 kg.",
        "lifespan": "Often around 20–25 years in the wild.",
        "fact": "A giraffe's long neck helps it reach vegetation high above the ground."
    },

    "Panda": {
        "emoji": "🐼",
        "appearance": "Giant pandas have a round body, black-and-white fur, four legs and a short tail.",
        "colour": "Distinctive black-and-white coat.",
        "body": "Four legs, large paws, strong jaws and teeth adapted for crushing bamboo.",
        "region": "Mountainous areas of central China.",
        "habitat": "Temperate mountain forests with bamboo.",
        "diet": "Mostly bamboo, although pandas can occasionally eat other foods.",
        "size": "About 1.2–1.9 metres long.",
        "weight": "Adults commonly weigh around 70–120 kg.",
        "lifespan": "Often around 15–20 years in the wild.",
        "fact": "Pandas have a specialized wrist bone that helps them hold bamboo."
    },

    "Monkey": {
        "emoji": "🐒",
        "appearance": "Monkeys have four limbs, a head, torso and often a tail.",
        "colour": "Extremely variable depending on species.",
        "body": "Four limbs, grasping hands and feet, and often a tail.",
        "region": "Africa, Asia, Central America and South America depending on species.",
        "habitat": "Forests, woodlands, grasslands and other environments.",
        "diet": "Often omnivorous; fruit, leaves, seeds, insects and other foods.",
        "size": "Ranges from very small species to much larger monkeys.",
        "weight": "Highly variable by species.",
        "lifespan": "Varies greatly by species.",
        "fact": "Monkeys are highly diverse, with many different species."
    },

    "Zebra": {
        "emoji": "🦓",
        "appearance": "Zebras have horse-like bodies, four legs, hooves, upright manes and stripes.",
        "colour": "Black-and-white striped coat.",
        "body": "Four legs ending in hooves, a mane, tail and strong teeth adapted for grazing.",
        "region": "Eastern and southern Africa, depending on species.",
        "habitat": "Grasslands, savannas and some woodland areas.",
        "diet": "Herbivorous; mainly grasses and other vegetation.",
        "size": "Medium-to-large hoofed mammals.",
        "weight": "Often around 175–450 kg depending on species.",
        "lifespan": "Often around 20–25 years in the wild.",
        "fact": "Each zebra has a unique pattern of stripes."
    }
}


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
