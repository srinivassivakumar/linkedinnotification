from app.services.openrouter_service import (
    analyze_connection,
    evaluate_employee_jobs,
    evaluate_founder_company
)

from app.services.web_search_service import (
    search_company_jobs,
    research_company
)

from app.services.connection_repository import (
    update_connection_result,
    get_connection_by_id
)

from app.services.telegram_service import (
    send_approval_card
)


# ============================================================
# PROCESS ONE LINKEDIN CONNECTION
# ============================================================

def process_connection(person):

    # --------------------------------------------------------
    # STEP 1: Identify founder or employee
    # --------------------------------------------------------

    first_result = analyze_connection(
        person["name"],
        person["current_title"],
        person["linkedin_url"]
    )

    person_type = first_result["person_type"]

    company = first_result.get(
        "company"
    )


    # ========================================================
    # STEP 2: EMPLOYEE BRANCH
    # ========================================================

    if person_type == "employee":

        # Company could not be identified
        if not company:

            return {
                "type": "employee",
                "company": None,
                "status": "manual_review",
                "reason": "Company could not be identified"
            }


        # ----------------------------------------------------
        # Search current jobs
        # ----------------------------------------------------

        results = search_company_jobs(
            company
        )


        # ----------------------------------------------------
        # Ask AI to evaluate jobs
        # ----------------------------------------------------

        result = evaluate_employee_jobs(
            name=person["name"],
            company=company,
            headline=person["current_title"],
            search_results=results
        )


        result["type"] = "employee"

        result["company"] = company


        # ----------------------------------------------------
        # NO MATCHING JOB
        # ----------------------------------------------------

        if not result.get(
            "matching_job_found",
            False
        ):

            first_name = (
                person["name"]
                .split()[0]
            )

            result["status"] = "no_matching_job"

            result["message"] = (
                f"Hi {first_name}, thanks for connecting. "
                f"Great to connect with someone at {company}. "
                f"I'm currently working across AI, data and "
                f"cloud engineering and would be glad to "
                f"stay in touch."
            )

            return result


        # ----------------------------------------------------
        # MATCHING JOB FOUND
        # ----------------------------------------------------

        result["status"] = "awaiting_approval"

        return result


    # ========================================================
    # STEP 3: FOUNDER BRANCH
    # ========================================================

    if person_type == "founder":

        # Company could not be identified
        if not company:

            return {
                "type": "founder",
                "company": None,
                "status": "manual_review",
                "reason": "Company could not be identified"
            }


        # ----------------------------------------------------
        # Research company
        # ----------------------------------------------------

        results = research_company(
            company
        )


        # ----------------------------------------------------
        # Ask AI to evaluate company
        # ----------------------------------------------------

        result = evaluate_founder_company(
            name=person["name"],
            company=company,
            headline=person["current_title"],
            search_results=results
        )


        result["type"] = "founder"

        result["company"] = company

        result["status"] = "awaiting_approval"


        return result


    # ========================================================
    # STEP 4: UNKNOWN PERSON
    # ========================================================

    return {
        "type": "unknown",
        "company": company,
        "status": "manual_review",
        "reason": (
            "Could not determine whether person "
            "is founder or employee"
        )
    }


# ============================================================
# PROCESS + SAVE + SEND TELEGRAM APPROVAL
# ============================================================

def process_and_send_for_approval(
    connection_id,
    person
):

    print()
    print("=" * 60)
    print("Processing connection")
    print("=" * 60)

    print(
        "Name:",
        person["name"]
    )

    print(
        "Title:",
        person["current_title"]
    )

    print(
        "LinkedIn:",
        person["linkedin_url"]
    )

    print()
    print(
        "Running AI + research..."
    )


    # ========================================================
    # STEP 1: RUN PROCESSING
    # ========================================================

    result = process_connection(
        person
    )


    print()
    print(
        "Processing result:"
    )

    print(result)


    # ========================================================
    # STEP 2: MANUAL REVIEW
    # ========================================================

    if result.get(
        "status"
    ) == "manual_review":

        print()
        print(
            "Manual review required."
        )

        print(
            "Reason:",
            result.get(
                "reason"
            )
        )

        return result


    # ========================================================
    # STEP 3: SAVE RESULT TO DATABASE
    # ========================================================

    update_connection_result(
        connection_id,
        result
    )


    print()
    print(
        "Result saved to database."
    )


    # ========================================================
    # STEP 4: NO MATCHING JOB
    # ========================================================

    if result.get(
        "status"
    ) == "no_matching_job":

        print()
        print(
            "No suitable job found."
        )

        print(
            "Simple networking message saved."
        )

        print(
            "Telegram approval card will NOT be sent."
        )

        return result


    # ========================================================
    # STEP 5: LOAD UPDATED DATABASE RECORD
    # ========================================================

    connection = get_connection_by_id(
        connection_id
    )


    if connection is None:

        raise RuntimeError(
            f"Connection {connection_id} "
            f"could not be loaded from database."
        )


    # ========================================================
    # STEP 6: SEND TELEGRAM APPROVAL
    # ========================================================

    if connection.get(
        "status"
    ) == "awaiting_approval":

        send_approval_card(
            connection
        )

        print()
        print(
            "Telegram approval card sent."
        )

        print(
            "Status:",
            connection.get(
                "status"
            )
        )


    return result