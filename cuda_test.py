import cv2
import numpy as np
from extras import *
import image as img
import win32gui
@timeit
def locateManyImage_CUDA(hwnd,template,region,threshold):
    img_rgb = cv2.imread('img/test.png')#img.screengrab_array(hwnd,region)
    gpu_img = cv2.cuda.GpuMat(img_rgb)#cv2.cuda_GpuMat(img_rgb)
    template = cv2.imread('img/'+template)
    gpu_template = cv2.cuda_GpuMat(template)
    gpu_result = cv2.cuda.createTemplateMatching(gpu_img.type(),gpu_img.type(), cv2.TM_CCOEFF_NORMED)
    gpu_result.match(gpu_img,gpu_template)
    result = gpu_result.download()
    result = cv2.threshold(result, threshold, 1, cv2.THRESH_TOZERO)[1]
    positions = cv2.findNonZero(result)
    return positions
@timeit
def locateManyImage(hwnd,file, region, thresh):
    img_rgb = img.screengrab_array(hwnd,region)

    template = cv2.imread('img/'+file)
    height, width, channels = template.shape
    h, w = template.shape[:-1]
    res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    threshold = thresh
    loc = np.where(res >= threshold)
    pos = []
    for pt in zip(*loc[::-1]):  # Switch collumns and rows
        #cv2.rectangle(img_rgb, pt, (pt[0] + w, pt[1] + h), (255, 0, 0),1)
        pt = (pt[0], pt[1], w, h)
        pos.append(pt)
    try:
        # print(time.time()-start_time)
        #img = PIL.Image.fromarray(img_rgb).show()
        return pos
    except:
        return False
    
if __name__ == "__main__":
    hwnd = 262522
    l,t,r,b = win32gui.GetWindowRect(hwnd)
    print(locateManyImage_CUDA(hwnd,'test_cross.png',(l,t,r-l,b-t),0.8))
    print(locateManyImage(hwnd,'test_cross.png',(l,t,r-l,b-t),0.8))