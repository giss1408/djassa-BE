# Fidelia — Dossier investisseur

*Pré-amorçage · Abidjan, Côte d'Ivoire · octobre 2026* · [English version](INVESTOR-BRIEF.md)

> **Éléments à compléter.** Tout ce qui est marqué `[À COMPLÉTER]` (immatriculation, actionnariat) est une donnée fictive à remplacer avant tout envoi. Les chiffres de marché sont sourcés dans [MARKET.md](MARKET.md) et doivent être revérifiés avant tout usage contractuel.
>
> Ce document est la traduction de [INVESTOR-BRIEF.md](INVESTOR-BRIEF.md). Toute modification doit être reportée dans les deux versions, ainsi que dans les pages web (`backend-api/app/investor_brief/`, servies derrière le mot de passe investisseur à `<API>/brief/`).

## En une phrase

**Fidelia aide les commerces de quartier à faire revenir leurs clients, et transforme leurs ventes de tous les jours en une preuve qu'un prêteur peut croire.**

## L'opportunité

- **2,72 M de points de paiement marchand** en Côte d'Ivoire en 2024, contre 1,13 M un an plus tôt (données BCEAO). Les commerçants passent au numérique, vite.
- Encaisser ne coûte presque plus rien (~1 % côté commerçant sur Wave). Ce qui manque est au-dessus : reconnaître le client, le faire revenir, prouver l'activité.
- Banques et IMF veulent prêter aux petits commerçants mais ne peuvent pas les évaluer : le taux de bancarisation strict est de **31,2 %** (BCEAO ; indicateurs nationaux 2023). Les programmes publics (APIF, SGPME, GUDE-PME) cherchent des partenaires privés pour combler cet écart.

## Le produit

| Quand | Ce que le commerçant obtient |
|---|---|
| Jour 1 | Un cahier de caisse : ventes en espèces et en mobile money dans un seul total du jour |
| Semaine 1 | La fidélité par numéro de téléphone, et chaque semaine le nombre de clients revenus et de nouveaux clients amenés par l'application Fidelia |
| Mois 3 et après | Un historique de ventes qui appartient au commerçant, présenté à un prêteur agréé uniquement avec son consentement |

Fidelia se branche sur le portefeuille que le commerçant utilise déjà (Wave d'abord, puis les autres opérateurs et le QR interopérable de **PI-SPI**, [détails](MARKET.md#what-pi-spi-is)) : pas de nouveau moyen de paiement, aucun frais en plus. Deux applications (commerçant et client) et la plateforme existent en prototypes fonctionnels.

**Fidelia ne détient jamais de fonds et ne prête jamais.** Les institutions agréées gardent la conservation des fonds et le crédit.

## Traction

**Pré-pilote. Pas encore d'utilisateurs, de commerçants ni de revenus.**

| Construit (prototypes, branche `integration`) | Preuves attendues de la phase 0 |
|---|---|
| Connexion par numéro de téléphone et code SMS | Entretiens avec 5 à 10 gérants de maquis et d'épiceries d'une commune |
| Ventes hors ligne, synchronisées sans doublon, testées sur un vrai téléphone | Lettres d'intérêt signées : commerçants et une IMF ([modèles](LETTERS-OF-INTEREST.fr.md)) |
| Points et récompenses ; alertes de bons plans ; « Client venu » au comptoir | Réponse de Wave sur l'accès à son API |
| Capture des paiements Wave du commerçant, en test | Un premier commerçant en conditions réelles |

## Le marché

| Niveau | Points de vente | Valeur par an | Construction |
|---|---:|---:|---|
| Total : commerçants qui acceptent le QR en Côte d'Ivoire | ~1 000 000 | ~90 Md FCFA | Commerçants QR Wave CI, ~1 M annoncés en 2026 ([MARKET.md](MARKET.md)) × 7 500 F × 12 |
| Accessible : maquis et épiceries à Abidjan | ~120 000 | ~10,8 Md FCFA (16,5 M€) | × 40 % à Abidjan × 30 % restauration, boissons et épicerie *(hypothèses)* |
| Objectif à 3 ans : commerçants payants | 1 800 | ~171 M FCFA de revenu annuel récurrent | 1,5 % du marché accessible |

*Estimation descendante : aucun recensement fiable des maquis et épiceries d'Abidjan n'existe. À vérifier en phase 0.*

## Modèle économique

| Source de revenu | Quand |
|---|---|
| Abonnement commerçant : formule gratuite plafonnée, puis ~5 000 F et ~10 000–15 000 F / mois / point de vente, payé en mobile money *(hypothèses à tester)* | Après le pilote (le pilote est gratuit) |
| Bons plans sponsorisés : emplacement ponctuel et limité dans le temps dans l'application client ; prix à tester | À partir de l'an 2 |
| Contrats multi-points de vente et réseaux | Après preuve |
| Commissions d'apport consenties (crédit, épargne) : Fidelia perçoit des frais de distribution, sans jamais porter de risque de crédit. **Absentes des prévisions** | Après partenariat |

**Pourquoi un commerçant paie :** un petit maquis qui gagne +5 % grâce aux clients qui reviennent dégage environ 73 000 F de marge brute par mois, pour un abonnement de 5 000 à 7 500 F (illustratif ; voir [BUSINESS-MODEL.md](BUSINESS-MODEL.md)).

## La concurrence

| Aujourd'hui | Ce qui manque | Fidelia |
|---|---|---|
| Cahier papier et cartes de fidélité | Aucun total, aucun client reconnu, aucune preuve | Cahier de caisse plus rapide, fidélité sans carte |
| Applications marchandes des portefeuilles (Wave, Orange Money, MTN MoMo) | Un seul opérateur chacune, pas les espèces, pas d'outil de fidélité trouvé | Tous les portefeuilles et les espèces ; partenaire, pas concurrent |
| WhatsApp Business et Facebook | Aucune vente enregistrée, aucune mesure du retour | Offres en notification, mesurées au comptoir |
| Applications de caisse avec fidélité | Pas reliées au mobile money, pas de preuve pour un prêteur | Capture des portefeuilles, hors ligne, preuve consentie |
| Agrégateurs de paiement (CinetPay) | ~3 % + 50 F par paiement, pas de fidélité | Ne détourne jamais les paiements |

Risque principal : qu'un opérateur ajoute la fidélité. Réponse : être le seul outil qui couvre tous les portefeuilles et les espèces, et la preuve que les IMF acceptent.

## Prévisions sur trois ans

| M FCFA | An 1 | An 2 | An 3 |
|---|---:|---:|---:|
| Commerçants payants en fin d'année | 100 | 600 | 1 800 |
| Revenus | 2,1 | 29,2 | 105,5 |
| Coûts totaux (an 1 : pilote de 30,8 inclus) | 47,2 | 73,5 | 164,0 |
| **Résultat net** | **−45,1** | **−44,4** | **−58,6** |
| Besoin de financement cumulé | 45,1 | 89,5 | 148,1 |

Les coûts fixes sont couverts à partir d'environ **1 250 commerçants payants**, atteints en année 3. Le besoin total, environ **148 M FCFA**, se finance en deux tours : ce tour pilote, puis un tour d'amorçage d'environ 120 M FCFA valorisé sur les résultats du pilote.

*Prévisions, pas des résultats. Hypothèses : abonnement moyen 7 500 F ; bons plans sponsorisés +400 F par commerçant dès l'an 2 ; 40 % des commerçants du pilote payants ; coût d'acquisition 40 000 F par nouveau commerçant ; coût variable 1 500 F par mois et par commerçant ; coûts fixes 2 M FCFA par mois après le pilote, puis 4 M (an 2) et 8 M (an 3) ; aucune commission partenaire.*

## Jalons financés par ce tour

Le tour finance le pilote de six mois, en deux tranches. Chaque tranche paie une phase ; la seconde n'est versée que lorsque le seuil de sortie de la première est atteint.

| Tranche · phase | Preuves exigées |
|---|---|
| **Tranche 1 · Phase 0 : découverte, conformité et préparation à la production** (mois 1–2) | 5 à 10 entretiens avec des gérants de maquis et d'épiceries dans une commune d'Abidjan ; accès à l'API Wave confirmé ; périmètre réglementaire et revue ARTCI ; un partenaire de paiement ; une ou deux IMF interrogées sur un outil consenti de suivi des ventes de leurs commerçants emprunteurs |
| **Tranche 2 · Phase 1 : pilote gratuit, 5 à 10 commerçants** (mois 3–6) | **Sortie :** ≥ 70 % des ventes réelles enregistrées au jour 30, vers 85 % au jour 60 ; l'application amène de nouveaux clients, enregistrés au comptoir ; ≥ 40 % des commerçants acceptent la formule payante à la fin du pilote gratuit |
| **Après ce tour** | Un tour d'amorçage valorisé sur les résultats du pilote. Puis le seuil d'économie unitaire avant toute deuxième commune : coût d'acquisition inférieur à 12 mois de marge brute, 3 mois de rétention, coût de support et de messagerie connu par point de vente |

## L'équipe

| | Rôle | Responsable de |
|---|---|---|
| **Stanislas Regisse** | CEO | Produit, technologie et sécurité |
| **Bienvenue Kouadio** | Marketing | Contact partenaires et investisseurs, finances, stratégie marketing |
| Responsable terrain | Recrutement, financé par ce tour | Intégration et suivi des commerçants |
| Conseillers | En cours de recrutement | Microfinance, mobile money, droit UEMOA |

## La société

| | |
|---|---|
| Entité juridique | `[À COMPLÉTER]` Fidelia SAS, Abidjan, Côte d'Ivoire (OHADA) |
| Immatriculation (RCCM) | `[À COMPLÉTER]` CI-ABJ-2026-B-00000 |
| Capital social | `[À COMPLÉTER]` 1 000 000 FCFA |
| Actionnariat | `[À COMPLÉTER]` Stanislas Regisse 50 % · Bienvenue Kouadio 50 % |
| Financement antérieur | `[À COMPLÉTER]` Aucun (fonds propres des fondateurs) |
| Propriété intellectuelle | `[À COMPLÉTER]` Code et marque cédés à la société |
| Nom de marque définitif | À confirmer juridiquement avant le lancement public |

## La levée

| | |
|---|---|
| Tour | Pré-amorçage, **tour pilote : 31 M FCFA (47 260 €, environ 53 000 USD)**. Il finance uniquement le pilote de six mois, tel que budgété dans [FINANCE-BUDGET.fr.md](FINANCE-BUDGET.fr.md) |
| Tranche 1, à la signature | **14 M FCFA (21 340 €)** pour les mois 1–2 : revue réglementaire et protection des données, préparation à la production (connexion par numéro, capture Wave, revue de sécurité), appareils de test |
| Tranche 2, au seuil de sortie de la phase 0 | **17 M FCFA (25 920 €)** pour les mois 3–6, le pilote sur le terrain. Versée quand un partenaire de paiement agréé est confirmé et que Wave a répondu sur l'accès à son API, que 5 à 10 maquis et épiceries ont signé l'accord de pilote, et que la revue de préparation à la production n'a plus de point critique ouvert |
| Instrument | BSA AIR adapté au droit OHADA (modèle ABAN, revu par un avocat OHADA) : ni intérêts ni remboursement ; converti en actions au prochain tour valorisé |
| Conditions | Plafond de valorisation **1,3 M USD post-money** (environ 4 % pour l'ensemble du tour) · décote de 20 % sur le prochain tour · mêmes conditions pour les deux tranches |
| Utilisation des fonds | Équipe 29 % · juridique, réglementaire et sécurité 15 % · produit et infrastructure 15 % · appareils de test 10 % · opérations terrain 8 % · lancement 6 % · administration 4 % · provision pour imprévus 13 % |
| Horizon | La fin du pilote (mois 6), quand le seuil de sortie de la phase 1 est mesuré |
| Prochain tour | Amorçage, valorisé sur les résultats du pilote, auprès de fonds qui investissent davantage à mesure que des indicateurs convenus sont atteints |
| Non dilutif | Subventions visées en parallèle (projet fintech de l'APIF-CI, facilité d'inclusion financière numérique de la BAD, develoPPP) ; une subvention réduit le montant levé |

*USD à environ 1 € = 1,13 USD (octobre 2026) ; le franc CFA est fixé à l'euro (1 € = 655,957 FCFA). Conditions proposées, à confirmer avec un avocat OHADA.*

## Le retour pour l'investisseur

Le tour pilote se convertit en actions au tour d'amorçage, avec une décote. À terme, la valeur vient d'un réseau de commerçants et de leurs historiques consentis, qui intéresse les opérateurs, les banques et IMF, et les fintechs régionales (Moniepoint a bâti son crédit sur ce type de données, [MARKET.md](MARKET.md)). Aucune sortie n'est promise : ce sont les chemins plausibles.

## Les risques

| Risque | Réponse |
|---|---|
| Wave refuse son API | La vente en espèces avec le numéro du client fonctionne sans Wave ; règle d'arrêt ou de changement si les commerçants refusent aussi ([CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries)) |
| Les commerçants arrêtent d'enregistrer | Cahier de caisse dès le jour 1 ; la part des ventes enregistrées est mesurée chaque semaine et décide de chaque étape |
| Réglementation | Fidelia ne détient pas de fonds et ne prête pas ; les partenaires agréés le font ; revue ARTCI et juridique en phase 0 |
| Petite équipe | Responsable terrain recruté pendant le pilote ; conseillers ; dépenses liées aux seuils |

**Lignes rouges :** aucune promesse de prêt, aucun dépôt détenu par Fidelia, aucune donnée partagée sans consentement, aucun score opaque, aucun lancement panafricain, aucune base biométrique réutilisable ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

## Contact

Bienvenue Kouadio (contact partenaires et investisseurs) · contact.fidelia@regisse.com

*Document d'information. Ne constitue ni une offre de services financiers, ni une offre de titres. Les chiffres issus de sources publiques sont cités dans [MARKET.md](MARKET.md) ; les calculs illustratifs sont signalés comme tels.*
