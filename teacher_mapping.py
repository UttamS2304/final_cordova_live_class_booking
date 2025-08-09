# Priority order within each list (first is primary)
TEACHER_MAP = {
    "Hindi": ["Bharti Ma'am"],
    "Mathematics": ["Vivek Sir"],
    "GK": ["Dakshika", "Ishita"],
    "SST": ["Ishita", "Shivangi"],
    "Science": ["Kalpana Ma'am", "Payal", "Sneha"],
    "English": ["Aparajita", "Deepanshi", "Megha"],
    "Pre Primary": ["Yaindrila Ma'am"],
    "EVS": ["Yaindrila Ma'am", "Kalpana Ma'am"],
    "Computer": ["Arpit", "Geetanjali"],
}

def candidates_for_subject(subject: str):
    return TEACHER_MAP.get(subject, [])
