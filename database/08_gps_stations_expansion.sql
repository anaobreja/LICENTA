-- Migrare 08: Extindere coordonate GPS pentru statii cheie pe coridoarele principale
-- Acoperire: coridoarele Buc-Brasov, Buc-Constanta, Buc-Cluj, Buc-Iasi/Moldova,
--            Buc-Craiova, Cluj-Brasov, si noduri de junctiune importante.

UPDATE stations SET latitude = 44.5240, longitude = 25.9824 WHERE code = 'CFR-30110'; -- Chitila
UPDATE stations SET latitude = 44.5648, longitude = 25.9895 WHERE code = 'CFR-30146'; -- Buftea Hm.
UPDATE stations SET latitude = 44.5949, longitude = 25.9911 WHERE code = 'CFR-30196'; -- Crivina Hm.
UPDATE stations SET latitude = 44.6236, longitude = 25.9867 WHERE code = 'CFR-30172'; -- Peris
UPDATE stations SET latitude = 44.9036, longitude = 25.9667 WHERE code = 'CFR-30225'; -- Brazi

-- Culoarul Bucuresti -> Brasov
UPDATE stations SET latitude = 44.9391, longitude = 25.9837 WHERE code = 'CFR-30304'; -- Ploiesti Vest
UPDATE stations SET latitude = 45.0921, longitude = 25.8091 WHERE code = 'CFR-30392'; -- Floresti Prahova Hm.
UPDATE stations SET latitude = 45.1217, longitude = 25.7374 WHERE code = 'CFR-30421'; -- Campina
UPDATE stations SET latitude = 45.2467, longitude = 25.6447 WHERE code = 'CFR-30483'; -- Comarnic Hm.
UPDATE stations SET latitude = 45.3614, longitude = 25.5994 WHERE code = 'CFR-30500'; -- Valea Larga Hm.
UPDATE stations SET latitude = 45.3528, longitude = 25.5503 WHERE code = 'CFR-30524'; -- Sinaia
UPDATE stations SET latitude = 45.4011, longitude = 25.5342 WHERE code = 'CFR-30548'; -- Busteni Hm.
UPDATE stations SET latitude = 45.4414, longitude = 25.5489 WHERE code = 'CFR-30550'; -- Azuga Hm.
UPDATE stations SET latitude = 45.5097, longitude = 25.5708 WHERE code = 'CFR-30615'; -- Predeal
UPDATE stations SET latitude = 45.5700, longitude = 25.5480 WHERE code = 'CFR-30641'; -- Timisu de Sus Hm.
UPDATE stations SET latitude = 45.6450, longitude = 25.6200 WHERE code = 'CFR-30665'; -- Darste Hm.

-- Culoarul Bucuresti -> Constanta
UPDATE stations SET latitude = 44.9780, longitude = 26.0600 WHERE code = 'CFR-30378'; -- Buda
UPDATE stations SET latitude = 44.9415, longitude = 26.0559 WHERE code = 'CFR-50079'; -- Ploiesti Est
UPDATE stations SET latitude = 44.9500, longitude = 26.1300 WHERE code = 'CFR-50122'; -- Valea Calugăreasca Hm.
UPDATE stations SET latitude = 44.9800, longitude = 26.1700 WHERE code = 'CFR-50160'; -- Cricov Hm.
UPDATE stations SET latitude = 45.0167, longitude = 26.4500 WHERE code = 'CFR-50213'; -- Mizil
UPDATE stations SET latitude = 45.1200, longitude = 26.5500 WHERE code = 'CFR-50263'; -- Ulmeni Hm.
UPDATE stations SET latitude = 45.1067, longitude = 26.7039 WHERE code = 'CFR-50237'; -- Sahăteni Hm.
UPDATE stations SET latitude = 45.2175, longitude = 26.8839 WHERE code = 'CFR-50184'; -- Inotesti Hm.
UPDATE stations SET latitude = 45.0533, longitude = 26.8250 WHERE code = 'CFR-72455'; -- Buzau Ram. Gr. A
UPDATE stations SET latitude = 44.3713, longitude = 27.8471 WHERE code = 'CFR-80505'; -- Fetesti
UPDATE stations SET latitude = 44.3936, longitude = 27.8567 WHERE code = 'CFR-80543'; -- Ramificatia Borcea Hm.
UPDATE stations SET latitude = 44.4007, longitude = 27.9830 WHERE code = 'CFR-80579'; -- Dunarea Hm.
UPDATE stations SET latitude = 44.3400, longitude = 28.0200 WHERE code = 'CFR-80581'; -- Cernavoda Pod
UPDATE stations SET latitude = 44.3067, longitude = 28.1967 WHERE code = 'CFR-80610'; -- Saligny Hm.
UPDATE stations SET latitude = 44.2480, longitude = 28.2740 WHERE code = 'CFR-80684'; -- Medgidia
UPDATE stations SET latitude = 44.2040, longitude = 28.4462 WHERE code = 'CFR-80634'; -- Mircea Voda Hm.
UPDATE stations SET latitude = 44.2789, longitude = 28.5575 WHERE code = 'CFR-80555'; -- Ovidiu Hm.
UPDATE stations SET latitude = 44.1622, longitude = 28.4358 WHERE code = 'CFR-80763'; -- Basarabi
UPDATE stations SET latitude = 44.1666, longitude = 28.3629 WHERE code = 'CFR-80775'; -- Valul lui Traian Hm.
UPDATE stations SET latitude = 44.1473, longitude = 28.5200 WHERE code = 'CFR-80749'; -- Dorobantu Hm.
UPDATE stations SET latitude = 44.1712, longitude = 28.5847 WHERE code = 'CFR-80830'; -- Palas
UPDATE stations SET latitude = 44.3600, longitude = 27.3700 WHERE code = 'CFR-80361'; -- Ciulnita
UPDATE stations SET latitude = 44.2460, longitude = 27.0450 WHERE code = 'CFR-80218'; -- Sarulesti (Bucuresti-Calarasi)
UPDATE stations SET latitude = 44.4416, longitude = 25.9988 WHERE code = 'CFR-10146'; -- Chiajna
UPDATE stations SET latitude = 44.4600, longitude = 26.0400 WHERE code = 'CFR-10108'; -- Bucurestii Noi Hm.
UPDATE stations SET latitude = 44.5400, longitude = 26.0167 WHERE code = 'CFR-70029'; -- Parc Mogosoia h.
UPDATE stations SET latitude = 44.5400, longitude = 26.0167 WHERE code = 'CFR-70031'; -- Mogosoia (Buc-Ploiesti via Snagov)

-- Culoarul Bucuresti -> Craiova -> Timisoara
UPDATE stations SET latitude = 44.1176, longitude = 24.9912 WHERE code = 'CFR-10445'; -- Rosiori Nord
UPDATE stations SET latitude = 44.2848, longitude = 25.5169 WHERE code = 'CFR-10287'; -- Videle

-- Culoarul Bucuresti -> Iasi (via Buzau-Bacau)
UPDATE stations SET latitude = 45.8826, longitude = 27.2348 WHERE code = 'CFR-50691'; -- Marasesti
UPDATE stations SET latitude = 45.8800, longitude = 27.2400 WHERE code = 'CFR-72560'; -- Marasesti Ram. Putna
UPDATE stations SET latitude = 45.6950, longitude = 27.1857 WHERE code = 'CFR-50499'; -- Focsani (daca exista)
UPDATE stations SET latitude = 46.0997, longitude = 27.1778 WHERE code = 'CFR-50759'; -- Adjud (daca exista)

-- Cluj-Napoca si zona
UPDATE stations SET latitude = 46.7712, longitude = 23.6236 WHERE code = 'CFR-32015'; -- Cluj-Napoca
UPDATE stations SET latitude = 46.7626, longitude = 23.6600 WHERE code = 'CFR-31982'; -- Cluj-Napoca Est
UPDATE stations SET latitude = 46.7893, longitude = 23.7133 WHERE code = 'CFR-31944'; -- Apahida Hm.

-- Culoarul Baia Mare -> Cluj -> Brasov
UPDATE stations SET latitude = 47.1300, longitude = 23.8750 WHERE code = 'CFR-41140'; -- Dej
UPDATE stations SET latitude = 46.5800, longitude = 23.7850 WHERE code = 'CFR-41394'; -- Turda
UPDATE stations SET latitude = 46.5570, longitude = 23.9050 WHERE code = 'CFR-41428'; -- Campia Turzii
UPDATE stations SET latitude = 46.1920, longitude = 23.7300 WHERE code = 'CFR-41462'; -- Teius
UPDATE stations SET latitude = 46.1760, longitude = 23.9200 WHERE code = 'CFR-41496'; -- Blaj (daca exista)

-- Alte noduri importante
UPDATE stations SET latitude = 44.2460, longitude = 27.0450 WHERE code = 'CFR-80270'; -- Dor Mărunt Hm. (Buc-Fetesti)
UPDATE stations SET latitude = 44.3100, longitude = 26.8000 WHERE code = 'CFR-80256'; -- Lehliu (Buc-Fetesti)
UPDATE stations SET latitude = 45.3844, longitude = 26.9356 WHERE code = 'CFR-50425'; -- Ramnicu Sarat (daca exista)
UPDATE stations SET latitude = 44.3067, longitude = 28.2100 WHERE code = 'CFR-89757'; -- Constanta P1

-- Verificare: culoarul Bucuresti Nord - aeroport
UPDATE stations SET latitude = 44.5715, longitude = 26.0850 WHERE code = 'CFR-70017'; -- Pajura Hm. (700) linie Buc-Otopeni
UPDATE stations SET latitude = 44.5715, longitude = 26.0800 WHERE code = 'CFR-70005'; -- R. Aeroport T1

-- Focsani corridor (Moldova)
UPDATE stations SET latitude = 45.6950, longitude = 27.1857 WHERE code = 'CFR-50499'; -- Focsani
UPDATE stations SET latitude = 46.0997, longitude = 27.1778 WHERE code = 'CFR-50759'; -- Adjud

-- Corectii GPS (coordonate gresite initial)
UPDATE stations SET latitude = 45.1447, longitude = 26.8277 WHERE code = 'CFR-50342'; -- Buzau (statia principala, nu junctiunea)

-- Braila era plasata eronat la coordonatele Focsaniului (45.74, 27.18)
-- Gara Braila reala: 45.2683 N, 27.9699 E
UPDATE stations SET latitude = 45.2683, longitude = 27.9699 WHERE name IN ('Brăila', 'Braila');

-- Tecuci era plasata eronat cu 33km prea la sud (45.52 in loc de 45.85)
-- Gara Tecuci reala: 45.8547 N, 27.4325 E
UPDATE stations SET latitude = 45.8547, longitude = 27.4325 WHERE name = 'Tecuci';

-- Cluj-Napoca centru universitar
UPDATE stations SET
    is_university_hub = TRUE,
    student_count = 80000,
    universities_count = 7,
    notes = 'Cel mai mare centru universitar din Transilvania; UBB, UTCN, UMF, USAMV Cluj-Napoca'
    WHERE code = 'CFR-32015'; -- Cluj-Napoca
