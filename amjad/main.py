from test_sparql import get_events
from generate_story import generate_story


events = get_events()

'''
qids = [e.split("/")[-1] for e in events]

timeline = build_timeline(qids)
'''

story = generate_story(events)

print("\nTIMELINE:\n")
for e in events:
    print(f"Date: {e['date']} - Event: {e['event']}")
    
print("\nSTORY:\n")
print(story)