import ctypes
import image as img
import numpy as np
import cv2
from PIL import Image
from extras import timeInMillis
tests = {"test1":11,"test2":8,"test3":6,"test4":8,"test5":4,"test6":7,"test7":6,"test8":17}
class Bot:

    def __init__(self):
        self.hp_colors = ((192,192,0),(96,192,96),(0,192,0),(192,48,48),(96, 0, 0),	(192, 0, 0))
        
    def dilate(self,img,iter = 1,ker = 8):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ker,ker))
        dilate = cv2.dilate(img, kernel, iterations=iter)
        return dilate
    def open(self,img,iter= 1, ker = 2):
        
        kernel = np.ones((ker,ker),np.uint8)
        opening = cv2.morphologyEx(img,cv2.MORPH_OPEN,kernel, iterations = iter)
        return opening
    
    def close(self,img,iter= 1,ker = 2):
        
        kernel = np.ones((ker,ker),np.uint8)
        closing = cv2.morphologyEx(img,cv2.MORPH_CLOSE,kernel, iterations = iter)
        return closing
    
    def distance_transform(self,img,mod = 0.6):
        dist_transform = cv2.distanceTransform(img,cv2.DIST_L2,5)
        #print(dist_transform.max())
        ret, thresh = cv2.threshold(dist_transform,mod*dist_transform.max(),255,0)
        thresh = np.uint8(thresh)
        return thresh
    
    def getMonstersAroundContours(self,image_name):
        
        start = timeInMillis()
        image = cv2.imread("img/"+image_name+".png")#Image.open("img/test.png")
        image = np.array(image)
        shape = image.shape
        contours_count = 0
        mask = np.full([shape[0],shape[1]],False)
        black_image = np.full_like(image, [0, 0, 0])
        red, green, blue = image[:,:,2], image[:,:,1], image[:,:,0]
        for color in self.hp_colors:
            r1, g1, b1 = color # Original value
            mask = (red == r1) & (green == g1) & (blue == b1)
            black_image[mask] = [255,255,255]
        #times[2] = timeInMillis()
        #black_image = self.dilate(black_image,1,2)
        black_image = self.open(black_image,1)
        black_image = self.dilate(black_image,1,8)

        black_image = cv2.cvtColor(black_image,cv2.COLOR_BGR2GRAY)

        black_image = cv2.threshold(black_image,128,255,cv2.THRESH_BINARY)[1]
        #if test:
            #print("thresh")
            #img.visualize(thresh)
        black_image = self.distance_transform(black_image,0.2)
        #
        
        #self.monsters_around_image = opening
        #cv2.imwrite("monsters_around.png",opening)
        #self.monsters_around_image = PhotoImage(file="monsters_around.png")
        #opening  =self.dilate(opening,3)
        #opening = self.distance_transform(opening,0.5)
        #opening = self.open(opening,1)
        contours,_ = cv2.findContours(black_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        #print(cont)
        #times[3] = timeInMillis()
        #print("---------")
        #for i in range(0,len(times)-1):
        #    print("time "+str(i)+": "+str(times[i+1]-times[i]))
        return (timeInMillis()-start,len(contours))
    def getMonstersAroundContoursNew(self,image):
        start = timeInMillis()
        test = False
        #image = cv2.imread("img/"+image_name+".png")#Image.open("img/test.png")
        #image = np.array(image)
        #if test:
        #    img.visualize(image)
        shape = image.shape
        contours_count = 0
        contours_list = []
        red, green, blue = image[:,:,2], image[:,:,1], image[:,:,0]
        #black_image_ = np.full_like(image, [0, 0, 0])
        #black_image_ = cv2.cvtColor(black_image_,cv2.COLOR_BGR2GRAY)
        #mask_ = np.full([shape[0],shape[1]],False)  
        for color in self.hp_colors:
            #mask = mask_
            #black_image = black_image_
            black_image = np.full_like(image, [0, 0, 0])
            mask = np.full([shape[0],shape[1]],False)
            r1, g1, b1 = color # Original value
            mask = (red == r1) & (green == g1) & (blue == b1)
            
            black_image[mask] = [255,255,255]
            #black_image = self.dilate(black_image,1,3)
            black_image = cv2.cvtColor(black_image,cv2.COLOR_BGR2GRAY)
            if test:
                img.visualize(black_image)
            #black_image = self.open(black_image,1)
            if test:
                img.visualize(black_image)
            
            black_image = self.close(black_image,2)
            
            black_image = self.open(black_image,1)
            
            if test:
                img.visualize(black_image)
            #times[2] = timeInMillis()
            black_image = self.dilate(black_image,1,8)
            #if test:
                
                #print("dilate")
            #    img.visualize(black_image)
            
            
   
            contours = cv2.findContours(black_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            #print(contours)
            contours_list.append(contours)
        
            if test:
                img.visualize(black_image)
            if test:
                print("contours: "+str(len(contours[0])))
            contours_count+=len(contours[0])

        return (timeInMillis()-start,contours_count,contours_list)
        #return (contours,opening)

    def new_test(self,image_name):
        start = timeInMillis()
        image = cv2.imread("img/"+image_name+".png")#Image.open("img/test.png")
        image = np.array(image)
        #if test:
        #    img.visualize(image)
        shape = image.shape
        
        ar = np.asarray(image) # get all pixels
        cols = 2
        rows = 2
        image = ar[::rows,::cols] 
        #image = Image.fromarray(pixels)
        #img.visualize(pixels)
        return (timeInMillis()-start,image)
if __name__ == "__main__":
    bot = Bot()
    time = 0
    amount = len(tests.keys())
    total = 0
    correct = 0
    for t in tests.keys():
        time_,image = bot.new_test(t)
        time+= time_
        time_, cont,_ = bot.getMonstersAroundContoursNew(image)
        time+= time_

        print(t + " "+str(cont)+"/"+str(tests[t]))
        total+= abs(cont- tests[t])
        '''
        time_, cont,_ = bot.getMonstersAroundContoursNew(image)
        time+= time_
        print(image + " "+str(cont)+"/"+str(tests[image]))
        total+= abs(cont- tests[image])
      '''  
    print("incorrect by: "+str(total))
    
    print("avg time: "+str(time/amount))