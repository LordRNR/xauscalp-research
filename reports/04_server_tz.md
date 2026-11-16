# Estudio 4 — Zona horaria del servidor MT5 (verificación empírica)

Servidor: MetaQuotes-Demo · offset al exportar: 7200 s · semanas: 252, confiables: 28

## Veredicto: **CONSISTENT**

- Base (min) de cada regla que explica TODAS las semanas confiables: {'fixed': None, 'base+US_DST': None, 'base+EU_DST': 120}
- Semanas que separan regla de EE. UU. y de la UE: 6
- Semanas a ambos lados de un cambio de hora: {'base+US_DST': True, 'base+EU_DST': True}
- **Declarar en el EA**: `InpTzPolicy=TZ_BASE_PLUS_EU_DST, InpTzBaseMinutes=120` · **paridad/Python**: `--tz base_dst:120:Europe/London`

Una única regla explica todas las semanas y los datos contienen las semanas capaces de refutar las alternativas.

| week | week_start_server | offset_min | corr | second_corr | n_overlap | confident |
|---|---|---|---|---|---|---|
| 1096 | 2021-01-02 12:00:00 | 120.000 | 0.997 | 0.035 | 6846 | True |
| 1097 | 2021-01-09 12:00:00 | 120.000 | 0.996 | 0.020 | 6841 | True |
| 1098 | 2021-01-16 12:00:00 | 120.000 | 0.819 | 0.031 | 6610 | True |
| 1099 | 2021-01-23 12:00:00 | 120.000 | 0.993 | 0.032 | 6832 | True |
| 1100 | 2021-01-30 12:00:00 | 120.000 | 0.992 | 0.027 | 6843 | True |
| 1101 | 2021-02-06 12:00:00 | 120.000 | 0.990 | 0.030 | 6843 | True |
| 1102 | 2021-02-13 12:00:00 | 120.000 | 0.991 | 0.038 | 6610 | True |
| 1103 | 2021-02-20 12:00:00 | 120.000 | 0.994 | 0.044 | 6841 | True |
| 1104 | 2021-02-27 12:00:00 | 120.000 | 0.996 | 0.028 | 5530 | True |
| 1105 | 2021-03-06 12:00:00 | 120.000 | 0.995 | 0.118 | 1314 | True |
| 1106 | 2021-03-13 12:00:00 | 120.000 | 0.995 | 0.024 | 6841 | True |
| 1107 | 2021-03-20 12:00:00 | 120.000 | 0.994 | 0.051 | 1481 | True |
| 1108 | NaT | nan | nan | nan | 0 | False |
| 1109 | NaT | nan | nan | nan | 0 | False |
| 1110 | NaT | nan | nan | nan | 0 | False |
| 1111 | NaT | nan | nan | nan | 0 | False |
| 1112 | NaT | nan | nan | nan | 0 | False |
| 1113 | NaT | nan | nan | nan | 0 | False |
| 1114 | NaT | nan | nan | nan | 0 | False |
| 1115 | NaT | nan | nan | nan | 0 | False |
| 1116 | NaT | nan | nan | nan | 0 | False |
| 1117 | NaT | nan | nan | nan | 0 | False |
| 1118 | NaT | nan | nan | nan | 0 | False |
| 1119 | NaT | nan | nan | nan | 0 | False |
| 1120 | NaT | nan | nan | nan | 0 | False |
| 1121 | NaT | nan | nan | nan | 0 | False |
| 1122 | NaT | nan | nan | nan | 0 | False |
| 1123 | NaT | nan | nan | nan | 0 | False |
| 1124 | NaT | nan | nan | nan | 0 | False |
| 1125 | NaT | nan | nan | nan | 0 | False |
| 1126 | NaT | nan | nan | nan | 0 | False |
| 1127 | NaT | nan | nan | nan | 0 | False |
| 1128 | NaT | nan | nan | nan | 0 | False |
| 1129 | NaT | nan | nan | nan | 0 | False |
| 1130 | NaT | nan | nan | nan | 0 | False |
| 1131 | NaT | nan | nan | nan | 0 | False |
| 1132 | NaT | nan | nan | nan | 0 | False |
| 1133 | NaT | nan | nan | nan | 0 | False |
| 1134 | NaT | nan | nan | nan | 0 | False |
| 1135 | NaT | nan | nan | nan | 0 | False |
| 1136 | NaT | nan | nan | nan | 0 | False |
| 1137 | NaT | nan | nan | nan | 0 | False |
| 1138 | NaT | nan | nan | nan | 0 | False |
| 1139 | NaT | nan | nan | nan | 0 | False |
| 1140 | NaT | nan | nan | nan | 0 | False |
| 1141 | NaT | nan | nan | nan | 0 | False |
| 1142 | NaT | nan | nan | nan | 0 | False |
| 1143 | NaT | nan | nan | nan | 0 | False |
| 1144 | NaT | nan | nan | nan | 0 | False |
| 1145 | NaT | nan | nan | nan | 0 | False |
| 1146 | NaT | nan | nan | nan | 0 | False |
| 1147 | NaT | nan | nan | nan | 0 | False |
| 1148 | NaT | nan | nan | nan | 0 | False |
| 1149 | NaT | nan | nan | nan | 0 | False |
| 1150 | NaT | nan | nan | nan | 0 | False |
| 1151 | NaT | nan | nan | nan | 0 | False |
| 1152 | NaT | nan | nan | nan | 0 | False |
| 1153 | NaT | nan | nan | nan | 0 | False |
| 1154 | NaT | nan | nan | nan | 0 | False |
| 1155 | NaT | nan | nan | nan | 0 | False |
| 1156 | NaT | nan | nan | nan | 0 | False |
| 1157 | NaT | nan | nan | nan | 0 | False |
| 1158 | NaT | nan | nan | nan | 0 | False |
| 1159 | NaT | nan | nan | nan | 0 | False |
| 1160 | NaT | nan | nan | nan | 0 | False |
| 1161 | NaT | nan | nan | nan | 0 | False |
| 1162 | NaT | nan | nan | nan | 0 | False |
| 1163 | NaT | nan | nan | nan | 0 | False |
| 1164 | NaT | nan | nan | nan | 0 | False |
| 1165 | NaT | nan | nan | nan | 0 | False |
| 1166 | NaT | nan | nan | nan | 0 | False |
| 1167 | NaT | nan | nan | nan | 0 | False |
| 1168 | NaT | nan | nan | nan | 0 | False |
| 1169 | NaT | nan | nan | nan | 0 | False |
| 1170 | NaT | nan | nan | nan | 0 | False |
| 1171 | NaT | nan | nan | nan | 0 | False |
| 1172 | NaT | nan | nan | nan | 0 | False |
| 1173 | NaT | nan | nan | nan | 0 | False |
| 1174 | NaT | nan | nan | nan | 0 | False |
| 1175 | NaT | nan | nan | nan | 0 | False |
| 1176 | NaT | nan | nan | nan | 0 | False |
| 1177 | NaT | nan | nan | nan | 0 | False |
| 1178 | NaT | nan | nan | nan | 0 | False |
| 1179 | NaT | nan | nan | nan | 0 | False |
| 1180 | NaT | nan | nan | nan | 0 | False |
| 1181 | NaT | nan | nan | nan | 0 | False |
| 1182 | NaT | nan | nan | nan | 0 | False |
| 1183 | NaT | nan | nan | nan | 0 | False |
| 1184 | NaT | nan | nan | nan | 0 | False |
| 1185 | NaT | nan | nan | nan | 0 | False |
| 1186 | NaT | nan | nan | nan | 0 | False |
| 1187 | NaT | nan | nan | nan | 0 | False |
| 1188 | NaT | nan | nan | nan | 0 | False |
| 1189 | NaT | nan | nan | nan | 0 | False |
| 1190 | NaT | nan | nan | nan | 0 | False |
| 1191 | NaT | nan | nan | nan | 0 | False |
| 1192 | NaT | nan | nan | nan | 0 | False |
| 1193 | NaT | nan | nan | nan | 0 | False |
| 1194 | NaT | nan | nan | nan | 0 | False |
| 1195 | NaT | nan | nan | nan | 0 | False |
| 1196 | NaT | nan | nan | nan | 0 | False |
| 1197 | NaT | nan | nan | nan | 0 | False |
| 1198 | NaT | nan | nan | nan | 0 | False |
| 1199 | NaT | nan | nan | nan | 0 | False |
| 1200 | NaT | nan | nan | nan | 0 | False |
| 1201 | NaT | nan | nan | nan | 0 | False |
| 1202 | NaT | nan | nan | nan | 0 | False |
| 1203 | NaT | nan | nan | nan | 0 | False |
| 1204 | NaT | nan | nan | nan | 0 | False |
| 1205 | NaT | nan | nan | nan | 0 | False |
| 1206 | NaT | nan | nan | nan | 0 | False |
| 1207 | NaT | nan | nan | nan | 0 | False |
| 1208 | NaT | nan | nan | nan | 0 | False |
| 1209 | NaT | nan | nan | nan | 0 | False |
| 1210 | NaT | nan | nan | nan | 0 | False |
| 1211 | NaT | nan | nan | nan | 0 | False |
| 1212 | NaT | nan | nan | nan | 0 | False |
| 1213 | NaT | nan | nan | nan | 0 | False |
| 1214 | NaT | nan | nan | nan | 0 | False |
| 1215 | NaT | nan | nan | nan | 0 | False |
| 1216 | NaT | nan | nan | nan | 0 | False |
| 1217 | NaT | nan | nan | nan | 0 | False |
| 1218 | NaT | nan | nan | nan | 0 | False |
| 1219 | NaT | nan | nan | nan | 0 | False |
| 1220 | NaT | nan | nan | nan | 0 | False |
| 1221 | NaT | nan | nan | nan | 0 | False |
| 1222 | NaT | nan | nan | nan | 0 | False |
| 1223 | NaT | nan | nan | nan | 0 | False |
| 1224 | NaT | nan | nan | nan | 0 | False |
| 1225 | NaT | nan | nan | nan | 0 | False |
| 1226 | NaT | nan | nan | nan | 0 | False |
| 1227 | NaT | nan | nan | nan | 0 | False |
| 1228 | NaT | nan | nan | nan | 0 | False |
| 1229 | NaT | nan | nan | nan | 0 | False |
| 1230 | NaT | nan | nan | nan | 0 | False |
| 1231 | NaT | nan | nan | nan | 0 | False |
| 1232 | NaT | nan | nan | nan | 0 | False |
| 1233 | NaT | nan | nan | nan | 0 | False |
| 1234 | NaT | nan | nan | nan | 0 | False |
| 1235 | NaT | nan | nan | nan | 0 | False |
| 1236 | NaT | nan | nan | nan | 0 | False |
| 1237 | NaT | nan | nan | nan | 0 | False |
| 1238 | NaT | nan | nan | nan | 0 | False |
| 1239 | NaT | nan | nan | nan | 0 | False |
| 1240 | NaT | nan | nan | nan | 0 | False |
| 1241 | NaT | nan | nan | nan | 0 | False |
| 1242 | NaT | nan | nan | nan | 0 | False |
| 1243 | NaT | nan | nan | nan | 0 | False |
| 1244 | NaT | nan | nan | nan | 0 | False |
| 1245 | NaT | nan | nan | nan | 0 | False |
| 1246 | NaT | nan | nan | nan | 0 | False |
| 1247 | NaT | nan | nan | nan | 0 | False |
| 1248 | NaT | nan | nan | nan | 0 | False |
| 1249 | NaT | nan | nan | nan | 0 | False |
| 1250 | NaT | nan | nan | nan | 0 | False |
| 1251 | NaT | nan | nan | nan | 0 | False |
| 1252 | NaT | nan | nan | nan | 0 | False |
| 1253 | NaT | nan | nan | nan | 0 | False |
| 1254 | NaT | nan | nan | nan | 0 | False |
| 1255 | NaT | nan | nan | nan | 0 | False |
| 1256 | NaT | nan | nan | nan | 0 | False |
| 1257 | NaT | nan | nan | nan | 0 | False |
| 1258 | NaT | nan | nan | nan | 0 | False |
| 1259 | NaT | nan | nan | nan | 0 | False |
| 1260 | NaT | nan | nan | nan | 0 | False |
| 1261 | 2024-03-02 12:00:00 | 120.000 | 0.983 | 0.064 | 6824 | True |
| 1262 | 2024-03-09 12:00:00 | 120.000 | 0.986 | 0.047 | 6880 | True |
| 1263 | 2024-03-16 12:00:00 | 120.000 | 0.995 | 0.027 | 6879 | True |
| 1264 | 2024-03-23 12:00:00 | 120.000 | 0.993 | 0.041 | 4131 | True |
| 1265 | 2024-03-30 12:00:00 | 180.000 | 0.996 | 0.026 | 6888 | True |
| 1266 | NaT | nan | nan | nan | 0 | False |
| 1267 | NaT | nan | nan | nan | 0 | False |
| 1268 | NaT | nan | nan | nan | 0 | False |
| 1269 | NaT | nan | nan | nan | 0 | False |
| 1270 | NaT | nan | nan | nan | 0 | False |
| 1271 | NaT | nan | nan | nan | 0 | False |
| 1272 | NaT | nan | nan | nan | 0 | False |
| 1273 | NaT | nan | nan | nan | 0 | False |
| 1274 | NaT | nan | nan | nan | 0 | False |
| 1275 | NaT | nan | nan | nan | 0 | False |
| 1276 | NaT | nan | nan | nan | 0 | False |
| 1277 | NaT | nan | nan | nan | 0 | False |
| 1278 | NaT | nan | nan | nan | 0 | False |
| 1279 | NaT | nan | nan | nan | 0 | False |
| 1280 | NaT | nan | nan | nan | 0 | False |
| 1281 | NaT | nan | nan | nan | 0 | False |
| 1282 | NaT | nan | nan | nan | 0 | False |
| 1283 | NaT | nan | nan | nan | 0 | False |
| 1284 | NaT | nan | nan | nan | 0 | False |
| 1285 | NaT | nan | nan | nan | 0 | False |
| 1286 | NaT | nan | nan | nan | 0 | False |
| 1287 | NaT | nan | nan | nan | 0 | False |
| 1288 | NaT | nan | nan | nan | 0 | False |
| 1289 | NaT | nan | nan | nan | 0 | False |
| 1290 | NaT | nan | nan | nan | 0 | False |
| 1291 | NaT | nan | nan | nan | 0 | False |
| 1292 | NaT | nan | nan | nan | 0 | False |
| 1293 | NaT | nan | nan | nan | 0 | False |
| 1294 | 2024-10-19 12:00:00 | 180.000 | 0.991 | 0.016 | 6761 | True |
| 1295 | NaT | nan | nan | nan | 0 | False |
| 1296 | NaT | nan | nan | nan | 0 | False |
| 1297 | NaT | nan | nan | nan | 0 | False |
| 1298 | NaT | nan | nan | nan | 0 | False |
| 1299 | NaT | nan | nan | nan | 0 | False |
| 1300 | NaT | nan | nan | nan | 0 | False |
| 1301 | NaT | nan | nan | nan | 0 | False |
| 1302 | NaT | nan | nan | nan | 0 | False |
| 1303 | NaT | nan | nan | nan | 0 | False |
| 1304 | NaT | nan | nan | nan | 0 | False |
| 1305 | NaT | nan | nan | nan | 0 | False |
| 1306 | NaT | nan | nan | nan | 0 | False |
| 1307 | NaT | nan | nan | nan | 0 | False |
| 1308 | NaT | nan | nan | nan | 0 | False |
| 1309 | NaT | nan | nan | nan | 0 | False |
| 1310 | NaT | nan | nan | nan | 0 | False |
| 1311 | NaT | nan | nan | nan | 0 | False |
| 1312 | NaT | nan | nan | nan | 0 | False |
| 1313 | 2025-03-01 12:00:00 | 120.000 | 0.991 | 0.030 | 4062 | True |
| 1314 | NaT | nan | nan | nan | 0 | False |
| 1315 | NaT | nan | nan | nan | 0 | False |
| 1316 | NaT | nan | nan | nan | 0 | False |
| 1317 | NaT | nan | nan | nan | 0 | False |
| 1318 | NaT | nan | nan | nan | 0 | False |
| 1319 | NaT | nan | nan | nan | 0 | False |
| 1320 | NaT | nan | nan | nan | 0 | False |
| 1321 | NaT | nan | nan | nan | 0 | False |
| 1322 | NaT | nan | nan | nan | 0 | False |
| 1323 | NaT | nan | nan | nan | 0 | False |
| 1324 | NaT | nan | nan | nan | 0 | False |
| 1325 | NaT | nan | nan | nan | 0 | False |
| 1326 | NaT | nan | nan | nan | 0 | False |
| 1327 | NaT | nan | nan | nan | 0 | False |
| 1328 | NaT | nan | nan | nan | 0 | False |
| 1329 | NaT | nan | nan | nan | 0 | False |
| 1330 | NaT | nan | nan | nan | 0 | False |
| 1331 | NaT | nan | nan | nan | 0 | False |
| 1332 | NaT | nan | nan | nan | 0 | False |
| 1333 | NaT | nan | nan | nan | 0 | False |
| 1334 | NaT | nan | nan | nan | 0 | False |
| 1335 | NaT | nan | nan | nan | 0 | False |
| 1336 | NaT | nan | nan | nan | 0 | False |
| 1337 | NaT | nan | nan | nan | 0 | False |
| 1338 | NaT | nan | nan | nan | 0 | False |
| 1339 | 2025-08-30 12:00:00 | 180.000 | 0.988 | 0.062 | 2622 | True |
| 1340 | 2025-09-06 12:00:00 | 180.000 | 0.988 | 0.022 | 6874 | True |
| 1341 | 2025-09-13 12:00:00 | 180.000 | 0.988 | 0.023 | 6890 | True |
| 1342 | 2025-09-20 12:00:00 | 180.000 | 0.985 | 0.024 | 4211 | True |
| 1343 | 2025-09-27 12:00:00 | 180.000 | 0.992 | 0.038 | 2634 | True |
| 1344 | 2025-10-04 12:00:00 | 180.000 | 0.989 | 0.042 | 5494 | True |
| 1345 | 2025-10-11 12:00:00 | 180.000 | 0.994 | 0.030 | 6879 | True |
| 1346 | 2025-10-18 12:00:00 | 180.000 | 0.995 | 0.030 | 6769 | True |
| 1347 | 2025-10-25 12:00:00 | 120.000 | 0.991 | 0.026 | 6881 | True |
