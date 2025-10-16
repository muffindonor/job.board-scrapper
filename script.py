# Identify and fix the column ordering bug
print("🐛 COLUMN ORDERING BUG IDENTIFIED!")
print("=" * 40)

print("❌ CURRENT BROKEN ORDER (Sheet2):")
print("  1. Title")
print("  2. Company") 
print("  3. Date Added (but contains Description!)")
print("  4. Description (but contains Qualifications!)")
print("  5. Qualifications (but contains Location!)")
print("  6. Location (but contains URL!)")
print("  7. URL (but contains Date Added!)")
print("  8. Missing: Date Posted")

print()
print("✅ CORRECT ORDER (Sheet3 format):")
print("  1. Title")
print("  2. Company")
print("  3. Date Posted")  
print("  4. Description")
print("  5. Qualifications")
print("  6. Location")
print("  7. URL")
print("  8. Date Added (with time)")

print()
print("🔍 ROOT CAUSE ANALYSIS:")
print("The row data preparation is misaligned with the headers!")

# Show the bug in the current code
current_bug = '''
HEADERS: ['Title', 'Company', 'Date Posted', 'Description', 'Qualifications', 'Location', 'URL', 'Date Added']

CURRENT BROKEN ROW PREPARATION:
row = [
    title,           # ✅ Correct (position 0)
    company,         # ✅ Correct (position 1) 
    date_added,      # ❌ Wrong! Should be date_posted (position 2)
    description,     # ❌ Wrong! Should be description (position 3) but shifts due to above
    qualifications,  # ❌ Wrong! Shifted
    location,        # ❌ Wrong! Shifted  
    url,            # ❌ Wrong! Shifted
    # Missing date_added with time!
]
'''

print(current_bug)

print()
print("🛠️ FIXES TO IMPLEMENT:")
print("=" * 25)
fixes = [
    "1. ✅ Fix row data order to match headers exactly",
    "2. ✅ Add timestamp to Date Added (YYYY-MM-DD HH:MM:SS)",  
    "3. ✅ Standardize all sheets (2,3,4) to same column structure",
    "4. ✅ Auto-sort by Date Added (newest first)",
    "5. ✅ Ensure Date Posted column is populated correctly"
]

for fix in fixes:
    print(fix)

print()
print("⏰ TIMESTAMP FORMAT:")
print("Current: '2025-10-16' (date only)")
print("New:     '2025-10-16 12:32:15' (date + time for precise sorting)")

print()
print("📊 AUTO-SORTING IMPLEMENTATION:")
print("After each batch write:")
print("1. Get all data from sheet")
print("2. Sort by Date Added column (descending)")  
print("3. Clear sheet and rewrite in sorted order")
print("4. Preserve formatting")

# Create the fix
fixed_code_preview = '''
# FIXED VERSION PREVIEW:

def save_to_sheet(self, sheet_name, jobs, headers, category):
    """Save jobs with CORRECT column order and auto-sorting"""
    
    # CORRECT row preparation (matches headers exactly)
    for job in jobs:
        row = [
            job.get('title', ''),                    # Position 0: Title
            job.get('company', ''),                  # Position 1: Company  
            job.get('date_posted', ''),              # Position 2: Date Posted
            job.get('description', ''),              # Position 3: Description
            job.get('qualifications', ''),           # Position 4: Qualifications
            job.get('location', ''),                 # Position 5: Location
            job.get('url', ''),                      # Position 6: URL
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Position 7: Date Added (with time!)
        ]
        all_rows.append(row)
    
    # Write batches...
    
    # AUTO-SORT after writing (newest first)
    self.sort_sheet_by_date_added(worksheet)

def sort_sheet_by_date_added(self, worksheet):
    """Sort sheet by Date Added column (newest to oldest)"""
    all_data = worksheet.get_all_values()
    if len(all_data) <= 1:
        return
        
    headers = all_data[0]
    data_rows = all_data[1:]
    
    # Sort by Date Added column (index 7) - newest first
    sorted_rows = sorted(data_rows, 
                        key=lambda x: x[7] if len(x) > 7 else '', 
                        reverse=True)
    
    # Clear and rewrite
    worksheet.clear()
    worksheet.append_row(headers)
    if sorted_rows:
        worksheet.append_rows(sorted_rows)
'''

print("🔧 PREVIEW OF FIXES:")
print(fixed_code_preview)

print()
print("✅ EXPECTED RESULT AFTER FIX:")
print("• All sheets have identical column structure")
print("• Data appears in correct columns") 
print("• Date Added includes precise timestamp")
print("• Sheets auto-sort by newest jobs first")
print("• No more manual sorting needed")

print()
print("Ready to implement the complete fix?")