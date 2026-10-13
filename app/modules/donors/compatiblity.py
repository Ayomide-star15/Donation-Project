"""Blood type compatibility — donor → recipients they can donate to."""


DONOR_CAN_HELP: dict[str, list[str]] = {
    "O-":  ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+":  ["O+", "A+", "B+", "AB+"],
    "A-":  ["A-", "A+", "AB-", "AB+"],
    "A+":  ["A+", "AB+"],
    "B-":  ["B-", "B+", "AB-", "AB+"],
    "B+":  ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}


def recipient_types_donor_can_help(donor_blood_type: str) -> list[str]:
    """What recipient blood types can this donor help with?"""
    return DONOR_CAN_HELP.get(donor_blood_type, [])