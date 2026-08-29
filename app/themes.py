THEMES = {
    "starry_night": {"name":"🌌 Starry Night","mode":"live","group":"Night & Space","bg":"linear-gradient(180deg,#03061a 0%,#07133b 48%,#160b34 100%)","effect":"stars shooting","accent":"#9f7cff"},
    "galaxy_glow": {"name":"🌠 Galaxy Glow","mode":"live","group":"Night & Space","bg":"radial-gradient(circle at 50% 35%,#6a2cff 0%,#170638 32%,#02051b 75%)","effect":"nebula stars","accent":"#b45cff"},
    "aurora_dream": {"name":"🌈 Aurora Dream","mode":"live","group":"Night & Space","bg":"linear-gradient(140deg,#021024,#073d3b,#34125b,#061b3c)","effect":"aurora stars","accent":"#5fffd6"},
    "ocean_night": {"name":"🌊 Ocean Night","mode":"live","group":"Night & Space","bg":"linear-gradient(180deg,#02091d,#063b69 65%,#01172c)","effect":"waves stars","accent":"#5ecbff"},
    "moonlight_garden": {"name":"🌙 Moonlight Garden","mode":"live","group":"Night & Space","bg":"linear-gradient(145deg,#07101d,#1a1640,#0b281f)","effect":"moon particles","accent":"#d8c4ff"},
    "city_lights": {"name":"🌃 City Lights","mode":"live","group":"Night & Space","bg":"linear-gradient(150deg,#03091a,#101b54,#2d0759)","effect":"stars neon","accent":"#4fb8ff"},
    "fireworks_night": {"name":"🎆 Fireworks Night","mode":"live","group":"Celebration","bg":"linear-gradient(180deg,#020617,#0d1740 65%,#2c0c37)","effect":"fireworks sparks","accent":"#ff66df"},
    "neon_fireworks": {"name":"🎇 Neon Fireworks","mode":"live","group":"Celebration","bg":"linear-gradient(145deg,#050011,#1b063b,#070028)","effect":"fireworks neon","accent":"#ff4fd8"},
    "royal_golden": {"name":"👑 Royal Golden","mode":"live","group":"Celebration","bg":"radial-gradient(circle at top,#563307,#160b03 58%,#050302)","effect":"gold particles","accent":"#ffd36a"},
    "golden_night": {"name":"✨ Golden Night","mode":"live","group":"Celebration","bg":"linear-gradient(145deg,#06080f,#342300,#0c0d18)","effect":"gold lights","accent":"#ffd15c"},
    "lantern_sky": {"name":"🏮 Lantern Sky","mode":"live","group":"Celebration","bg":"linear-gradient(180deg,#13061c,#3b1122,#12091b)","effect":"lanterns stars","accent":"#ffb35c"},
    "fairy_lights": {"name":"💡 Fairy Lights","mode":"live","group":"Celebration","bg":"linear-gradient(145deg,#100b22,#2a1438,#111528)","effect":"lights particles","accent":"#ffd56d"},
    "neon_love": {"name":"💖 Neon Love","mode":"live","group":"Love","bg":"radial-gradient(circle,#2d0b35 0%,#0c0824 55%,#02020b 100%)","effect":"hearts neon","accent":"#ff5fb4"},
    "rose_glow": {"name":"🌹 Rose Glow","mode":"live","group":"Love","bg":"linear-gradient(145deg,#25020c,#520d27,#120615)","effect":"petals hearts","accent":"#ff799e"},
    "purple_dream": {"name":"🔮 Mystic Purple","mode":"live","group":"Love","bg":"linear-gradient(145deg,#120525,#35105b,#07153a)","effect":"particles stars","accent":"#c786ff"},
    "starlight_terrace": {"name":"🌟 Starlight Terrace","mode":"live","group":"Love","bg":"linear-gradient(180deg,#050916,#13203b,#1a0d25)","effect":"lights stars","accent":"#ffd785"},
    "balloon_party": {"name":"🎈 Balloon Party","mode":"static","group":"Fun","bg":"linear-gradient(145deg,#9b1cf0,#ff4f9c,#ff9f4d)","effect":"balloons","accent":"#ffffff"},
    "rainy_window": {"name":"🌧 Rainy Window","mode":"live","group":"Fun","bg":"linear-gradient(145deg,#172638,#0c1423,#25384b)","effect":"rain drops","accent":"#a8d7ff"},
    "sunset_bloom": {"name":"🌺 Sunset Bloom","mode":"static","group":"Fun","bg":"linear-gradient(145deg,#ff5d7a,#ff925c,#6a2ca0)","effect":"flowers","accent":"#fff1dc"},
    "minimal_white": {"name":"🤍 Elegant Minimal","mode":"static","group":"Elegant","bg":"linear-gradient(145deg,#f5f1ec,#d8d2ca)","effect":"none","accent":"#5d4334"},
    "black_gold": {"name":"🖤 Black & Gold","mode":"static","group":"Elegant","bg":"linear-gradient(145deg,#050505,#201807,#080808)","effect":"gold particles","accent":"#ffd15c"},
    "pastel_dream": {"name":"🫧 Pastel Dream","mode":"static","group":"Elegant","bg":"linear-gradient(145deg,#c9b9ff,#ffb9d8,#a7e8ff)","effect":"bubbles","accent":"#ffffff"},
}

CATEGORY_ICONS = {
    "birthday":"🎂", "valentine":"❤️", "anniversary":"💍", "friendship":"👫",
    "congratulations":"🎉", "surprise":"🎁", "festival":"✨", "custom":"🌟"
}


# Premium cinematic themes. These are separate from the normal theme catalog so
# premium users can choose a theme designed specifically for their occasion.
PREMIUM_THEMES = {
    # Birthday
    "birthday_cake": {"name":"🎂 Luxury Cake Story","category":"birthday","accent":"#ff8aa5","bg":"linear-gradient(145deg,#2a0715,#6d1635,#ff7b9a)","effect":"confetti"},
    "birthday_party": {"name":"🎆 Neon Birthday Party","category":"birthday","accent":"#ffd36a","bg":"linear-gradient(145deg,#090025,#3c1268,#ef397e)","effect":"fireworks"},
    "birthday_starry": {"name":"🌌 Birthday Under Stars","category":"birthday","accent":"#9fc7ff","bg":"linear-gradient(180deg,#020617,#12224d,#2a124d)","effect":"stars"},
    "birthday_soft": {"name":"🧁 Soft Pastel Birthday","category":"birthday","accent":"#ff7da7","bg":"linear-gradient(145deg,#ffd4df,#cdbdff,#a8e8ff)","effect":"bubbles"},
    # Valentine
    "valentine_rose": {"name":"🌹 Rose Love Story","category":"valentine","accent":"#ff6f9f","bg":"linear-gradient(145deg,#18030b,#63162e,#23051c)","effect":"petals"},
    "valentine_neon": {"name":"💖 Neon Love Night","category":"valentine","accent":"#ff58bd","bg":"radial-gradient(circle at top,#5d174b,#140523 60%,#020207)","effect":"hearts"},
    "valentine_stars": {"name":"🌙 Starlit Romance","category":"valentine","accent":"#ffd6ec","bg":"linear-gradient(180deg,#05091e,#1c123b,#461329)","effect":"stars"},
    "valentine_luxury": {"name":"💎 Black Rose Luxury","category":"valentine","accent":"#f5b1c9","bg":"linear-gradient(145deg,#050505,#2a0715,#08030b)","effect":"sparkles"},
    # Anniversary
    "anniversary_gold": {"name":"🥂 Golden Anniversary","category":"anniversary","accent":"#ffd36a","bg":"linear-gradient(145deg,#120c02,#493000,#150a02)","effect":"gold"},
    "anniversary_memory": {"name":"📖 Our Memory Journey","category":"anniversary","accent":"#f4c9ff","bg":"linear-gradient(145deg,#180d28,#40235d,#1a0f26)","effect":"stars"},
    "anniversary_roses": {"name":"🌹 Forever & Always","category":"anniversary","accent":"#ff9bbd","bg":"linear-gradient(145deg,#25020b,#5a1532,#1a0710)","effect":"petals"},
    # Friendship
    "friendship_fun": {"name":"🫶 Besties Forever","category":"friendship","accent":"#7be7ff","bg":"linear-gradient(145deg,#132052,#3c1673,#ff5d91)","effect":"confetti"},
    "friendship_memory": {"name":"📸 Crazy Memories","category":"friendship","accent":"#ffd978","bg":"linear-gradient(145deg,#17384d,#4c296b,#f56f88)","effect":"sparkles"},
    "friendship_night": {"name":"🌃 Late Night Besties","category":"friendship","accent":"#a9baff","bg":"linear-gradient(180deg,#03061a,#101c4b,#271344)","effect":"stars"},
    # Congratulations
    "congrats_gold": {"name":"🏆 Golden Victory","category":"congratulations","accent":"#ffd15c","bg":"linear-gradient(145deg,#090702,#4c3300,#130b03)","effect":"gold"},
    "congrats_fireworks": {"name":"🎇 Victory Fireworks","category":"congratulations","accent":"#ff8de1","bg":"linear-gradient(145deg,#05051a,#221050,#4b093f)","effect":"fireworks"},
    # Surprise
    "surprise_mystery": {"name":"🎁 Mystery Reveal","category":"surprise","accent":"#b98cff","bg":"radial-gradient(circle at top,#311759,#10061e,#03030a)","effect":"stars"},
    "surprise_magic": {"name":"✨ Magical Portal","category":"surprise","accent":"#7bffe2","bg":"linear-gradient(145deg,#021b28,#0d3c4a,#27134d)","effect":"sparkles"},
    # Festival
    "festival_lantern": {"name":"🏮 Festival Lanterns","category":"festival","accent":"#ffb45f","bg":"linear-gradient(180deg,#1b061c,#57152a,#1b0717)","effect":"lanterns"},
    "festival_lights": {"name":"✨ Festival Lights","category":"festival","accent":"#ffe07d","bg":"linear-gradient(145deg,#10102b,#2f1650,#103548)","effect":"lights"},
    # Custom / universal
    "custom_universe": {"name":"🌌 Midnight Universe","category":"all","accent":"#9f7cff","bg":"linear-gradient(180deg,#03061a,#07133b,#160b34)","effect":"stars"},
    "custom_royal": {"name":"👑 Royal Luxury","category":"all","accent":"#ffd36a","bg":"radial-gradient(circle at top,#563307,#160b03 58%,#050302)","effect":"gold"},
    "custom_cinematic": {"name":"🎬 Cinematic Story","category":"all","accent":"#7be7ff","bg":"linear-gradient(145deg,#030714,#172654,#260f43)","effect":"sparkles"},
}
