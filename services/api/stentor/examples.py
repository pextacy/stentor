"""Example alerts for the composer dropdown. Written by us in NWS / FEMA style.
Each one is also in an eval suite, so its expected result is tested."""

EXAMPLES = [
    {"id": "wildfire-demo", "label": "Wildfire: evacuate via a route (demo)",
     "text": "Wildfire near ⟦Altadena⟧. EVACUATE NOW via Lake Ave. Do NOT return until 6:00 PM. Info: 211."},
    {"id": "hurricane", "label": "Hurricane Milton: mandatory evacuation",
     "text": "Hurricane Milton: residents of Pinellas County must evacuate now. Do not return until officials say it is safe."},
    {"id": "tsunami", "label": "Tsunami: higher ground, stay off the beach",
     "text": "Tsunami warning. Move to higher ground immediately. Stay away from the beach until 3 pm tomorrow."},
    {"id": "flash-flood", "label": "Flash flood: two prohibitions",
     "text": "Flash flood warning for Ellicott City. Move to higher ground now. Do not drive through flood water. Do not touch downed power lines."},
    {"id": "hazmat", "label": "Chemical spill: shelter in place",
     "text": "Chemical hazard warning for Deer Park. Shelter in place now. Close all windows and doors. Turn off air conditioning. Do not go outside until 6 PM."},
    {"id": "heat", "label": "Heat wave: indoors between two times",
     "text": "Heat wave in Ankara: stay indoors between 11:00 and 16:00. Drink plenty of water."},
    {"id": "earthquake", "label": "Earthquake: aftershocks",
     "text": "Earthquake warning for Izmir. Stay alert for updates. Expect aftershocks. Stay out of damaged buildings. Do not use elevators."},
    {"id": "tornado", "label": "Tornado: basement, away from windows",
     "text": "Tornado warning for Moore until 7:45 PM. Take shelter now in a basement. Stay away from windows."},
    {"id": "boil", "label": "Boil water advisory",
     "text": "Boil water advisory for Jackson until Friday. Boil water for one minute."},
    {"id": "all-clear", "label": "All clear: warning cancelled",
     "text": "All clear. The tsunami warning for Hilo has been cancelled. You may return home."},
    {"id": "review", "label": "Needs review: a condition templates cannot express",
     "text": "Active shooter at Lincoln High School. Shelter in place now. Lock doors and stay quiet. Call 911 if safe."},
]
