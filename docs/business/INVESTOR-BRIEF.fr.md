# Djassa — Dossier investisseur

*Pré-amorçage · Abidjan, Côte d'Ivoire · octobre 2026* · [English version](INVESTOR-BRIEF.md)

> **Éléments à compléter.** Tout ce qui est marqué `[À COMPLÉTER]` (immatriculation, actionnariat, levée) est une donnée fictive à remplacer avant tout envoi. Les chiffres de marché sont sourcés dans [MARKET.md](MARKET.md) et doivent être revérifiés avant tout usage contractuel.
>
> Ce document est la traduction de [INVESTOR-BRIEF.md](INVESTOR-BRIEF.md). Toute modification doit être reportée dans les deux versions, ainsi que dans la page web (`djassa-Web/public/brief/`).

## En une phrase

**Djassa transforme les ventes quotidiennes des commerces de quartier en preuve : un historique d'activité vérifié, qui appartient au commerçant et qu'il peut, avec son consentement, présenter à un prêteur agréé.** Le commerçant paie parce que Djassa fait revenir ses clients.

## Le problème

- La Côte d'Ivoire compte **plus de 25 millions de comptes mobile money actifs**, mais un **taux de bancarisation strict de 31,2 %** (BCEAO ; indicateurs nationaux 2023). L'accès au paiement est largement acquis ; **la preuve d'activité ne l'est pas**.
- Un maquis, une pharmacie ou une épicerie a des clients fidèles mais **aucun historique de ventes exploitable**, donc pas de crédit de trésorerie ou de stock. Les PME pèsent ~20 % du PIB et se heurtent à des garanties qu'elles ne peuvent pas fournir.
- La fidélité tient sur des cartes papier et la mémoire. Rien ne fait revenir un habitué volontairement.

## Le produit

Une seule habitude, enregistrer la vente, produit cinq usages : fidélité, historique de revenus, régularité de tontine, indicateur de fiabilité et dossier de financement pour un partenaire agréé.

- **Zéro effort en mobile money.** Djassa s'appuie sur le portefeuille que le commerçant utilise déjà. Les paiements sur son QR existant sont capturés automatiquement, Wave d'abord, puis les autres opérateurs et le QR interopérable de **PI-SPI**, la plateforme de la banque centrale (BCEAO) qui relie toutes les banques et tous les portefeuilles mobiles de la zone UEMOA ([détails](MARKET.md#what-pi-spi-is)). **Aucun frais en plus, aucune nouvelle habitude.**
- **Les espèces comptent aussi.** Un geste dans l'application commerçant, même hors ligne. Avec le numéro du client, celui-ci gagne des points.
- **Une fidélité visible pour le commerçant.** Points, récompenses remises au comptoir, bons plans, et chaque semaine le nombre de « clients revenus ».
- **Une preuve pour le crédit, avec consentement.** Chaque vente est étiquetée *confirmée par le prestataire* ou *déclarée par le commerçant*, et n'est exportée qu'avec consentement vers une IMF ou un fonds de garantie agréés.
- **Quatre briques :** une application commerçant (hors ligne d'abord, Android d'entrée de gamme), une application client (maquis, pharmacies de garde, bons plans, paiement, points), la plateforme, et un site public.

**Djassa ne détient jamais de fonds et ne prête jamais.** Les institutions agréées gardent la conservation des fonds et le crédit. Djassa est le partenaire technologique et de distribution.

## Pourquoi maintenant

- **Le paiement marchand décolle :** 2,72 millions de points de paiement marchand en Côte d'Ivoire en 2024, contre 1,13 million en 2023. Il représente 23,3 % du volume mobile money, contre 3,3 % en 2020 (données BCEAO).
- **Encaisser est devenu une commodité** (~1 % côté marchand sur Wave). Ce qui manque se situe au-dessus : reconnaître le client et prouver l'activité.
- **La BCEAO** a ouvert un chantier sur le scoring de crédit alternatif et lancé **PI-SPI** (paiements instantanés interopérables, obligatoires depuis juin 2026). Les programmes publics (APIF, SGPME, GUDE-PME) cherchent des partenaires d'exécution privés.
- **Comparables :** au Nigeria, les prêts de Moniepoint fondés sur les données de paiement ont été suivis de **+36 %** de valeur de transactions. Au Kenya, Kopo Kopo a observé **+42 %** de croissance des transactions après ses avances de trésorerie.

## Modèle économique

Logiciel marchand d'abord, infrastructure financière ensuite.

| Source de revenu | Quand |
|---|---|
| Abonnement commerçant : formule gratuite plafonnée, puis ~5 000 F et ~10 000–15 000 F / mois / point de vente *(hypothèses à tester)* | Pilote |
| Bons plans à la une (emplacement payant dans l'application client) et campagnes | Pilote |
| Contrats multi-points de vente et réseaux | Après preuve |
| Commissions d'apport consenties (crédit, épargne, tontine) : Djassa perçoit une commission de distribution, sans jamais porter le risque de crédit | Après partenariat |

**Pourquoi le commerçant paie :** un petit maquis qui gagne +5 % grâce aux clients qui reviennent dégage environ 73 000 F de marge brute par mois, pour un abonnement de 5 000 F (illustratif ; voir [BUSINESS-MODEL.md](BUSINESS-MODEL.md)). Faire passer ses paiements par un agrégateur à ~3 % lui coûterait davantage. C'est pourquoi Djassa ne remplace jamais le portefeuille du commerçant.

## Positionnement

Djassa évite les finances personnelles grand public (Djamo) et le paiement B2B (Julaya, Hub2), et s'associe aux rails de paiement (Wave, Orange, MTN, CinetPay). **La fidélité client et la preuve d'activité marchande** n'ont pas d'acteur ivoirien dominant.

## Traction

**Pré-pilote. Pas encore d'utilisateurs, de commerçants ni de revenus.** Ce qui existe, ce sont des prototypes fonctionnels (branche `integration`) :

- Une application commerçant qui enregistre les ventes hors ligne, testée sur un vrai téléphone, sans doublon après une coupure réseau.
- Une application client : découverte, pharmacies de garde, bons plans, paiement QR en mode sandbox et points.
- **Des points sur les ventes en espèces par numéro de téléphone**, avec solde consulté et récompense remise au comptoir.
- **Un seul historique de ventes** étiqueté selon la preuve, des emplacements à la une vendus, un registre de facturation, et un export consenti et audité.
- Un site public conçu pour le bas débit (~120 Ko à la première visite, fonctionne hors ligne).

## Jalons financés par ce tour

| Étape | Preuve attendue |
|---|---|
| **Phase 0 : découverte et conformité** | 5 à 10 entretiens commerçants sur un corridor d'Abidjan ; accès à l'API Wave confirmé ; périmètre réglementaire et revue ARTCI ; un partenaire de paiement |
| **Phase 1 : pilote avec 5 à 10 commerçants** | Connexion par numéro (OTP), capture Wave automatique, un partenaire de paiement en production. **Sortie :** les commerçants enregistrent la plupart de leurs ventes réelles pendant 60 jours ou plus, et paient ou renouvellent |
| **Seuil d'économie unitaire** | Coût d'acquisition inférieur à 12 mois de marge brute ; 3 mois de rétention ; coûts de support et de messagerie connus par point de vente |

Aucune expansion géographique avant qu'un corridor ait franchi ce seuil.

## L'équipe

| | Rôle | Responsabilités |
|---|---|---|
| **Stanislas Regisse** | CEO | Mise en œuvre technique et sécurité |
| **Bienvenue Kouadio** | Marketing | Contact partenaires et investisseurs, finances, stratégie marketing |

## La société

| | |
|---|---|
| Entité juridique | `[À COMPLÉTER]` Djassa SAS, Abidjan, Côte d'Ivoire (OHADA) |
| Immatriculation (RCCM) | `[À COMPLÉTER]` CI-ABJ-2026-B-00000 |
| Capital social | `[À COMPLÉTER]` 1 000 000 FCFA |
| Actionnariat | `[À COMPLÉTER]` Stanislas Regisse 50 % · Bienvenue Kouadio 50 % |
| Financement antérieur | `[À COMPLÉTER]` Aucun (fonds propres des fondateurs) |
| Propriété intellectuelle | `[À COMPLÉTER]` Code et marque cédés à la société |
| Nom de marque définitif | À confirmer juridiquement avant le lancement public |

## La levée

| | |
|---|---|
| Tour | `[À COMPLÉTER]` Pré-amorçage |
| Montant | `[À COMPLÉTER]` 000 000 USD |
| Instrument | `[À COMPLÉTER]` SAFE / obligation convertible, plafond à convenir |
| Utilisation des fonds (12 à 18 mois) | `[À COMPLÉTER]` Opérations du pilote et équipe terrain ~35 % · produit (connexion OTP, capture des portefeuilles, deuxième opérateur) ~35 % · juridique, réglementaire et revue de sécurité ~15 % · marketing et partenariats ~15 % |
| Horizon | Seuil de sortie de la phase 1 : un corridor pilote qui démontre rétention et renouvellement payant |

## Nos lignes rouges

Aucune promesse de prêt. Aucun dépôt détenu par Djassa. Aucune donnée partagée sans consentement. Aucun score opaque. Aucun lancement panafricain. Aucune base biométrique réutilisable. Ces principes déterminent ce que nous construisons et ce que nous refusons de vendre ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

## Contact

Bienvenue Kouadio (contact partenaires et investisseurs) · ptck2e@duck.mail

*Document d'information. Ne constitue ni une offre de services financiers, ni une offre de titres. Les chiffres issus de sources publiques sont cités dans [MARKET.md](MARKET.md) ; les calculs illustratifs sont signalés comme tels.*
