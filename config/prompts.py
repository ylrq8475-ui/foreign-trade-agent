from __future__ import annotations

from config.factory_profile import factory_context_summary


def build_profile_prompt(customer: dict, website_text: str) -> str:
    manual_note = str(customer.get("manual_research_note", "")).strip()
    return (
        "You are a B2B outbound research assistant. "
        "Read the target company's public website content and return a structured customer profile. "
        "Do not invent facts. Distinguish facts from inference. Prefer concise, commercially useful output.\n\n"
        f"Customer name: {customer.get('company_name', '')}\n"
        f"Country: {customer.get('country', '')}\n"
        f"Website: {customer.get('website', '')}\n"
        f"Known industry: {customer.get('industry', '')}\n"
        f"Manual research note: {manual_note}\n"
        "Website content:\n"
        f"{website_text[:4000]}"
    ).strip()


def build_email_prompt(customer: dict, profile: dict, company_context: dict) -> str:
    factory_summary = company_context.get("factory_summary") or factory_context_summary()
    factory_knowledge_summary = str(company_context.get("factory_knowledge_summary", "")).strip()
    matched_strengths = company_context.get("matched_strengths", [])
    matched_strengths_text = "\n".join(f"- {item}" for item in matched_strengths) or "- Use only clearly relevant factory strengths."
    manual_note = str(customer.get("manual_research_note", "")).strip()
    skill_guidance = str(company_context.get("skill_guidance", "")).strip()
    skill_company_profile = str(company_context.get("skill_company_profile", "")).strip()
    skill_block = ""
    if skill_guidance:
        skill_block += (
            "\n\nFactory Customer Email Match skill guidance:\n"
            f"{skill_guidance[:6000]}"
        )
    if skill_company_profile:
        skill_block += (
            "\n\nFactory Customer Email Match company profile reference:\n"
            f"{skill_company_profile[:4000]}"
        )
    return (
        "You are a professional export sales rep writing a short English cold email.\n"
        "Write a natural, low-AI-sounding outreach email that combines one real customer observation with one or two relevant supplier strengths.\n"
        "Rules:\n"
        "1. The first paragraph must reference real information from the customer's website or evidence.\n"
        "2. Present us as a stable silicone kitchenware manufacturer and professional supplier, not as a factory trying to impress with size.\n"
        "3. Use only strengths that logically match the customer's business type, assortment, or sourcing model.\n"
        "4. Do not list every advantage. Select the smallest useful combination.\n"
        "5. Avoid hype like 'leading manufacturer', 'best price', or generic praise.\n"
        "6. Lean toward signals buyers care about: stable quality, clear communication, reliable lead times, and relevant OEM/private-label support.\n"
        "7. Keep the email concise, professional, and easy to reply to.\n"
        "8. End with one light question only.\n"
        "9. Do not invent customer facts.\n"
        "10. Do not describe the customer as a private-label buyer unless the website evidence clearly supports private labeling or OEM cooperation.\n"
        "11. If the website only suggests brand ownership or assortment breadth, use a softer brand or assortment expansion angle instead.\n\n"
        "12. Prefer natural trade language over polished marketing language.\n"
        "13. Avoid phrases such as 'broad range', 'for your team', or 'for reference' unless they sound necessary and grounded.\n"
        "14. If the website evidence supports it, add one light market-signal sentence about repeat-order demand, assortment extension, or channel fit.\n"
        "15. Mention one relevant product family, one practical cooperation strength, and at most one short credibility cue.\n"
        "16. The email should sound like a real export salesperson writing manually, not like AI summary text.\n\n"
        f"Customer info:\n{profile}\n\n"
        f"Manual research note:\n{manual_note or '-'}\n\n"
        f"Our company summary:\n{factory_summary}\n\n"
        f"Stored verified factory facts:\n{factory_knowledge_summary or '-'}\n\n"
        f"Recommended matched strengths:\n{matched_strengths_text}\n\n"
        f"Our company type: {company_context.get('your_company_type', '')}\n"
        f"Our product focus: {company_context.get('your_products', '')}\n"
        f"Our default advantage line: {company_context.get('your_advantage', '')}"
        f"{skill_block}"
    ).strip()
