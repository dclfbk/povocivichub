URL="https://siatservices.provincia.tn.it/idt/raster/lidar_2009_pat_dtm_1mX1m/"
TIFFS="dtm001053_wor.tif  dtm001054_wor.tif  dtm001055_wor.tif  dtm001056_wor.tif  dtm001102_wor.tif  dtm001103_wor.tif  dtm001104_wor.tif  dtm001151_wor.tif  dtm001152_wor.tif  dtm001199_wor.tif"
for F in $TIFFS:
do
	wget $URL/$F
done
