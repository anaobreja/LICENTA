-- Coordonate GPS pentru centrele universitare si hub-urile feroviare majore
-- Sursa: Wikipedia + OpenStreetMap (verificate manual, WGS84)

-- 1. Bucuresti (UPB, ASE, UB, UMF Carol Davila, SNSPA, UNATC, UNMB, UNARTE)
UPDATE stations SET latitude = 44.4499, longitude = 26.0717,
  is_university_hub = TRUE, student_count = 200000, universities_count = 8,
  notes = 'UPB, ASE, UB, UMF Carol Davila, SNSPA, UNATC, UNMB, UNARTE'
WHERE name = 'Bucureşti Nord Gr.A';

-- 2. Cluj-Napoca (UBB, UTCN, UMF Cluj, USAMV)
UPDATE stations SET latitude = 46.7869, longitude = 23.5828,
  is_university_hub = TRUE, student_count = 100000, universities_count = 4,
  notes = 'UBB, UTCN, UMF Cluj, USAMV Cluj'
WHERE name IN ('Cluj Napoca', 'Cluj-Napoca');

-- 3. Iasi (UAIC, TUIASI, UMF Iasi, USAMV)
UPDATE stations SET latitude = 47.1664, longitude = 27.5868,
  is_university_hub = TRUE, student_count = 60000, universities_count = 4,
  notes = 'UAIC, TUIASI, UMF Grigore T. Popa, USAMV Iasi'
WHERE name IN ('Iaşi', 'Iasi');

-- 4. Timisoara (UVT, UPT, UMF Timisoara, USAMVB)
UPDATE stations SET latitude = 45.7515, longitude = 21.2098,
  is_university_hub = TRUE, student_count = 40000, universities_count = 4,
  notes = 'UVT, UPT, UMF Timisoara, USAMVB'
WHERE name IN ('Timişoara Nord', 'Timisoara Nord');

-- 5. Brasov (UNITBV)
UPDATE stations SET latitude = 45.6536, longitude = 25.5894,
  is_university_hub = TRUE, student_count = 20000, universities_count = 1,
  notes = 'Universitatea Transilvania Brasov'
WHERE name = 'Braşov';

-- 6. Sibiu (ULBS)
UPDATE stations SET latitude = 45.7944, longitude = 24.1499,
  is_university_hub = TRUE, student_count = 15000, universities_count = 1,
  notes = 'Universitatea Lucian Blaga Sibiu'
WHERE name = 'Sibiu';

-- 7. Craiova (UCV, UMF Craiova)
UPDATE stations SET latitude = 44.3308, longitude = 23.7917,
  is_university_hub = TRUE, student_count = 20000, universities_count = 2,
  notes = 'Universitatea Craiova, UMF Craiova'
WHERE name = 'Craiova';

-- 8. Constanta (UOC, Universitatea Maritima)
UPDATE stations SET latitude = 44.1733, longitude = 28.6383,
  is_university_hub = TRUE, student_count = 15000, universities_count = 2,
  notes = 'Universitatea Ovidius, Universitatea Maritima'
WHERE name IN ('Constanţa', 'Constanta');

-- 9. Oradea (UO)
UPDATE stations SET latitude = 47.0586, longitude = 21.9489,
  is_university_hub = TRUE, student_count = 15000, universities_count = 1,
  notes = 'Universitatea din Oradea'
WHERE name = 'Oradea';

-- 10. Galati (UDJG)
UPDATE stations SET latitude = 45.4353, longitude = 28.0541,
  is_university_hub = TRUE, student_count = 15000, universities_count = 1,
  notes = 'Universitatea Dunarea de Jos'
WHERE name IN ('Galaţi', 'Galati');

-- 11. Suceava (USV)
UPDATE stations SET latitude = 47.6614, longitude = 26.2497,
  is_university_hub = TRUE, student_count = 10000, universities_count = 1,
  notes = 'Universitatea Stefan cel Mare Suceava'
WHERE name IN ('Suceava', 'Suceava Burdujeni');

-- 12. Bacau (UBc)
UPDATE stations SET latitude = 46.5670, longitude = 26.9135,
  is_university_hub = TRUE, student_count = 8000, universities_count = 1,
  notes = 'Universitatea Vasile Alecsandri Bacau'
WHERE name IN ('Bacău', 'Bacau');

-- 13. Ploiesti (UPG)
UPDATE stations SET latitude = 44.9395, longitude = 26.0276,
  is_university_hub = TRUE, student_count = 10000, universities_count = 1,
  notes = 'Universitatea Petrol-Gaze Ploiesti'
WHERE name IN ('Ploieşti Sud', 'Ploiesti Sud');

-- 14. Arad (UVVG, UAV)
UPDATE stations SET latitude = 46.1781, longitude = 21.3133,
  is_university_hub = TRUE, student_count = 10000, universities_count = 2,
  notes = 'Univ Vasile Goldis, Univ Aurel Vlaicu'
WHERE name = 'Arad';

-- 15. Targu Mures (UMFST)
UPDATE stations SET latitude = 46.5468, longitude = 24.5573,
  is_university_hub = TRUE, student_count = 12000, universities_count = 2,
  notes = 'UMF George E. Palade, UMFST'
WHERE name IN ('Târgu Mureş', 'Targu Mures');

-- 16. Pitesti (UPIT)
UPDATE stations SET latitude = 44.8543, longitude = 24.8694,
  is_university_hub = TRUE, student_count = 8000, universities_count = 1,
  notes = 'Universitatea din Pitesti'
WHERE name IN ('Piteşti', 'Pitesti');

-- 17. Baia Mare (UTCN-NUC)
UPDATE stations SET latitude = 47.6592, longitude = 23.5795,
  is_university_hub = TRUE, student_count = 6000, universities_count = 1,
  notes = 'UTCN - Centrul Universitar Nord'
WHERE name = 'Baia Mare';

-- 18. Alba Iulia (UAB)
UPDATE stations SET latitude = 46.0667, longitude = 23.5800,
  is_university_hub = TRUE, student_count = 6000, universities_count = 1,
  notes = 'Universitatea 1 Decembrie 1918 Alba Iulia'
WHERE name = 'Alba Iulia';

-- 19. Targoviste (UVT-TGV)
UPDATE stations SET latitude = 44.9293, longitude = 25.4581,
  is_university_hub = TRUE, student_count = 6000, universities_count = 1,
  notes = 'Universitatea Valahia Targoviste'
WHERE name IN ('Târgovişte', 'Targoviste');

-- 20. Resita (UEM)
UPDATE stations SET latitude = 45.3001, longitude = 21.8865,
  is_university_hub = FALSE, student_count = 3000, universities_count = 1,
  notes = 'Universitatea Eftimie Murgu Resita'
WHERE name IN ('Reşiţa Sud', 'Resita Sud');

-- Hub-uri feroviare importante (fara universitati majore, doar conexiuni)
UPDATE stations SET latitude = 45.0494, longitude = 26.8067,
  notes = 'Hub feroviar - intersectie Moldova-Muntenia'
WHERE name IN ('Buzău', 'Buzau');

UPDATE stations SET latitude = 45.7458, longitude = 27.1855,
  notes = 'Hub feroviar - poarta Galati-Braila'
WHERE name IN ('Brăila', 'Braila');

UPDATE stations SET latitude = 46.7667, longitude = 22.9000,
  notes = 'Hub feroviar - poarta Transilvania de Vest'
WHERE name = 'Huedin';

UPDATE stations SET latitude = 45.5167, longitude = 27.2833,
  notes = 'Hub feroviar - nod Tecuci'
WHERE name = 'Tecuci';

UPDATE stations SET latitude = 47.2486, longitude = 26.7281,
  notes = 'Hub feroviar - nod Pascani'
WHERE name IN ('Paşcani', 'Pascani');

UPDATE stations SET latitude = 46.9417, longitude = 26.9322,
  notes = 'Nod feroviar Roman'
WHERE name = 'Roman';

UPDATE stations SET latitude = 45.8528, longitude = 23.0125,
  notes = 'Nod feroviar Simeria'
WHERE name = 'Simeria';

UPDATE stations SET latitude = 45.8786, longitude = 22.9089,
  notes = 'Hub Hateg-Petrosani'
WHERE name = 'Deva';

UPDATE stations SET latitude = 45.4153, longitude = 23.3550,
  notes = 'Nod feroviar Petrosani - Valea Jiului'
WHERE name IN ('Petroşani', 'Petrosani');

UPDATE stations SET latitude = 45.1167, longitude = 24.3667,
  notes = 'Hub feroviar Ramnicu Valcea'
WHERE name IN ('Râmnicu Vâlcea', 'Ramnicu Valcea');

-- Bucuresti - alte statii principale
UPDATE stations SET latitude = 44.4378, longitude = 26.1025,
  notes = 'Bucuresti Baneasa - hub Nord'
WHERE name LIKE 'Bucureşti Băneasa%';

UPDATE stations SET latitude = 44.4096, longitude = 26.1376,
  notes = 'Bucuresti Obor - hub Est'
WHERE name LIKE 'Bucureşti Obor%';
