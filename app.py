import streamlit as st

st.title("🐾 Animal Explorer")
st.write("Choose an animal to learn about it!")

animals = {
    "Dog": {
        "emoji": "🐶",
        "fact": "Dogs are domesticated mammals and are known for their strong bond with humans."
    },
    "Cat": {
        "emoji": "🐱",
        "fact": "Cats are small mammals known for their agility, sharp senses, and independent behavior."
    },
    "Lion": {
        "emoji": "🦁",
        "fact": "Lions are large social cats that live mainly in grasslands and savannas."
    },
    "Tiger": {
        "emoji": "🐯",
        "fact": "Tigers are large striped cats and are excellent swimmers."
    },
    "Elephant": {
        "emoji": "🐘",
        "fact": "Elephants are the largest living land animals and use their trunks for many tasks."
    },
    "Horse": {
        "emoji": "🐴",
        "fact": "Horses are strong mammals that have been domesticated by humans for thousands of years."
    },
    "Giraffe": {
        "emoji": "🦒",
        "fact": "Giraffes are the tallest living land animals."
    },
    "Panda": {
        "emoji": "🐼",
        "fact": "Giant pandas mainly eat bamboo and are native to China."
    },
    "Monkey": {
        "emoji": "🐒",
        "fact": "Monkeys are intelligent primates with many different species found around the world."
    },
    "Zebra": {
        "emoji": "🦓",
        "fact": "Zebras are African mammals famous for their distinctive black-and-white stripes."
    }
}

animal = st.selectbox(
    "Which animal do you want to learn about?",
    list(animals.keys())
)

if st.button("Learn About Animal"):

    info = animals[animal]

    st.header(info["emoji"] + " " + animal)

    st.write(info["fact"]) 
