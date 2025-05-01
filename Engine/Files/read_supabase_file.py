import requests

url = "https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/panelitix/The%20Big%20Question/Predictive%20Report/Question%20Context/question_context_test.txt"

response = requests.get(url)

if response.status_code == 200:
    print("📄 File Contents:\n")
    print(response.text)
else:
    print("❌ Failed to fetch file. Status:", response.status_code)
