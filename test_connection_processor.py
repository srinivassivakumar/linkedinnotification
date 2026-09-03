from app.services.connection_processor import process_connection


person = {
    "name": "Rohan Sharma",
    "current_title": "Founder & CEO at XYZ AI",
    "linkedin_url": "https://www.linkedin.com/in/example"
}


result = process_connection(person)


print("\nRESULT:")
print(result)