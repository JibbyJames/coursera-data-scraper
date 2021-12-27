# -*- coding: utf-8 -*-
import json
import time
import urllib.request
import pandas as pd
import numpy as np
import seaborn as sns
from matplotlib import pyplot as plt


def expand_list(df, list_column, new_column): 
    lens_of_lists = df[list_column].apply(len)
    origin_rows = range(df.shape[0])
    destination_rows = np.repeat(origin_rows, lens_of_lists)
    non_list_cols = (
      [idx for idx, col in enumerate(df.columns)
       if col != list_column]
    )
    expanded_df = df.iloc[destination_rows, non_list_cols].copy()
    expanded_df[new_column] = (
      [item for items in df[list_column] for item in items]
      )
    expanded_df.reset_index(inplace=True, drop=True)
    return expanded_df

run_locally = True
wait_length = 0.5

algolia_url = 'https://lua9b20g37-dsn.algolia.net/1/indexes/test_products?x-algolia-application-id=LUA9B20G37&x-algolia-api-key=dcc55281ffd7ba6f24c3a9b18288499b&hitsPerPage=1000&page='
product_pages = 4

## Fetch the data ##########################################################

if(run_locally):
    print(f"Reading courses from local file courses.json.")
    courses_df = pd.read_json('courses.json', orient='records')
    print(f"Reading courses from local file specializations.json.")
    specs_df = pd.read_json('specializations.json', orient='records') 
else:    
    all_products_list = []
    
    # Loop through each of the pages returned for the all products request
    for i in range(0, product_pages + 1):
        
        # Request data from algolia for current page
        with urllib.request.urlopen(f'{algolia_url}{i}') as url:
            print(f"Fetching coursera program data on page {i}.")
            page_data = json.loads(url.read().decode())
            
            # Save page data to local json file.
            with open(f'all-products-{i}.json', 'w') as outfile:
                json.dump(page_data, outfile)
                
            # Merge all products data into single list.
            all_products_list = all_products_list + page_data['hits']
            
        # Wait before scraping next data
        time.sleep(wait_length)  
            
    # Convert raw products json data into datframe
    all_products_df = pd.DataFrame.from_dict(all_products_list)
    
    # Group Courses, and clean data before creating dict
    courses_df = all_products_df.loc[all_products_df['entityType'] == 'COURSE'].reset_index(drop=True)
    courses_df['id'] = courses_df.apply(lambda row: row['objectID'].replace('course~',''), axis=1)
    courses_df = courses_df.set_index('id')
    courses = courses_df.to_dict('index')
    
    # Group Specializations, and clean data before creating dict
    specs_df = all_products_df.loc[all_products_df['entityType'] == 'SPECIALIZATION'].reset_index(drop=True)
    specs_df['id'] = specs_df.apply(lambda row: row['objectID'].replace('s12n~',''), axis=1)
    specs_df = specs_df.set_index('id')
    specs = specs_df.to_dict('index')
    
    # Loop through all specializations to collect their courses
    loop_length = len(specs.keys())
    for index, spec_id in enumerate(list(specs.keys())[:loop_length]):
        
        # Get specialization URL
        specs[spec_id]['courses'] = []        
        spec_row = specs[spec_id]        
        slug = spec_row['objectUrl'].replace("/specializations/", "")
        
        print(f"[{index+1}/{loop_length}] - Fetching course data for \"{slug}\"")
        
        spec_url = f"https://www.coursera.org/api/onDemandSpecializations.v1?q=slug&slug={slug}&fields=courseIds,id"
    
        # Make a request to that URL
        with urllib.request.urlopen(spec_url) as url:

            # Parse the JSON response.            
            spec_data = json.loads(url.read().decode())            
            course_ids = spec_data['elements'][0]['courseIds']
            
            # Loop through each course
            for course_id in course_ids:
                
                # Check that we have a record of this course already from Algolia  
                if course_id not in courses:
                    print(f"    - {course_id} - 404")
                else:    
                    
                    # Initialize specs array for course if required.
                    if 'specializations' not in courses[course_id].keys():
                        courses[course_id]['specializations'] = []
                    
                    print(f"    - {courses[course_id]['name']}")
                    
                    # Add Specialization to Course, and vice versa
                    if spec_id not in courses[course_id]['specializations']:
                        courses[course_id]['specializations'].append(spec_id)                
                    if course_id not in specs[spec_id]['courses']:
                        specs[spec_id]['courses'].append(course_id)
              
        # Wait before scraping next data
        time.sleep(wait_length)
    
    # Convert back to DF and save to local JSON
    specs_df = pd.DataFrame.from_dict(specs, orient='index')
    specs_df.to_json('specializations.json')
    
    # Pricing Data for courses
    loop_length = len(courses.keys())
    for index, course_id in enumerate(list(courses.keys())[:loop_length]):
           
        print(f"[{index+1}/{loop_length}] - Fetching price data for \"{courses[course_id]['name']}\"")
        
        courses[course_id]['price'] = 0
        
        price_url = f"https://www.coursera.org/api/productPrices.v3/VerifiedCertificate~{course_id}~GBP~GB"
        
        try:
            with urllib.request.urlopen(price_url) as url:            
                price_data = json.loads(url.read().decode())
                courses[course_id]['price'] = price_data['elements'][0]['amount']
                print(f'{courses[course_id]["name"]}: £{courses[course_id]["price"]}')
        except:
            print(f'{courses[course_id]["name"]}: ERROR - Not found')
    
        # Wait before scraping next data
        time.sleep(wait_length)   
    
    # Convert back to DF and save to JSON
    courses_df = pd.DataFrame.from_dict(courses, orient='index')
    courses_df.to_json('courses.json')


## Aggregate metrics ###########################################
    
# Add some fields for later use
specs_df['partners_str'] = specs_df.apply(lambda x : 'Offered by ' +  ' & '.join(x['partners']),axis=1)
specs_df['specialization'] = specs_df['name'] + '\n' + specs_df['partners_str']
courses_df['partners_str'] = courses_df.apply(lambda x : 'Offered by ' +  ' & '.join(x['partners']),axis=1)
courses_df['course'] = courses_df['name'] + '\n' + courses_df['partners_str']

# Expand the lists we want to aggregate in the specializations table
specs_df['courses'] = specs_df['courses'].apply(lambda d: d if isinstance(d, list) else [])
specs_with_expanded_courses_df = expand_list(specs_df, 'courses', 'course_id')
specs_with_expanded_partners_df = expand_list(specs_df, 'partners', 'partner_name')

# Join to the courses dataframe for additional metrics and clean columns names.
merged_specs_df = pd.merge(specs_with_expanded_courses_df, courses_df, left_on='course_id', right_index=True)
aggd_specs_df = merged_specs_df.groupby('specialization', as_index=False).sum()[['specialization','avgLearningHours_y','price']]
aggd_specs_df.rename(columns={'avgLearningHours_y': 'avgLearningHours', 'avgLearningHours_y': 'avgLearningHours'}, inplace=True)

## Plot some graphs ############################################

# Init Seaborn style
sns.set(style="whitegrid")

# What are some general stats on all specializations?
fig, axes = plt.subplots(4, 1)
sns.boxplot(x='enrollments', data=specs_df, ax=axes[0])
sns.boxplot(x='avgLearningHours', data=aggd_specs_df, ax=axes[1])
sns.boxplot(x='price', data=aggd_specs_df, ax=axes[2])
sns.boxplot(x='avgProductRating', data=specs_df, ax=axes[3])

# What are the most popular specializations?
top_specs_enrollments = specs_df.nlargest(15,'enrollments')
sns.barplot(x="enrollments", y="specialization", data=top_specs_enrollments)

# What are the most popular courses?
top_courses_enrollments = courses_df.nlargest(15,'enrollments')
sns.barplot(x="enrollments", y="course", data=courses_df)




# Are popular courses generally rated higher? (min number of enrollments)
sns.scatterplot(x="enrollments", y="avgProductRating", data=specs_df)


#courses_df.boxplot()

# Do longer courses have fewer enrollments?
    # Scatter

# Do more expensive courses have fewer enrollments?
    # Scatter

# Is there an organisation that provides the best courses?

# Does specialization duration have an impact on enrollments or reviews?

# Does price?

# What are the top ten courses by enrollments










