import re


def normalize_phone_number(phone: str) -> str:
    """Normalize phone numbers consistently by removing non-digits, except leading plus."""
    if not phone:
        return ""
    
    # Keep leading '+' if present
    has_plus = phone.strip().startswith('+')
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    if not digits:
        return ""
        
    return f"+{digits}" if has_plus else digits
