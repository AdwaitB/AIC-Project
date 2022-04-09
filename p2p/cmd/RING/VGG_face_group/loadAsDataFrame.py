import glob
import os
import pandas as pd

#path = "./vgg_face2/n001878/"

#li = []
#os.chdir(path)
#for file in glob.glob("*.jpg"):
#    img = file
#    # print(path+file)
#    li.append(path+file)

#ones = ["1"] * len(li)

#output = pd.DataFrame(list(zip(li, ones)), columns =['File_Path', 'Labels'])

#output.to_csv("../../Path_with_labels.csv",index=False)
levels = ['Normal', 'COVID']
path = "./COVID-19_Radiography_Dataset"
data_dir = os.path.join(path)

data = []
for id, level in enumerate(levels):
    for file in os.listdir(os.path.join(data_dir , level)):
        data.append(['{}/{}'.format(level, file), level])

data = pd.DataFrame(data, columns = ['image_file', 'corona_result'])

data['path'] = path + '/' + data['image_file']
data['corona_result'] = data['corona_result'].map({'Normal': 'Negative', 'COVID': 'Positive'})

data.to_csv("../../Path_with_labels.csv",index=False)