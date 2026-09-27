# Djassa Labs *(nom provisoire — à remplacer par le nom final choisi)*

> Un écosystème d'applications numériques pensées pour l'Afrique de l'Ouest, en partant de la Côte d'Ivoire.

## 🎯 Vision

Construire une famille d'applications qui répondent à des besoins réels et non couverts du marché ouest-africain — commerce local, inclusion financière, agriculture, santé, éducation — en s'appuyant sur une infrastructure déjà mature dans la région : le mobile money (Wave, Orange Money, MTN MoMo, Moov Money).

L'ambition n'est pas de copier des modèles occidentaux, mais de concevoir des produits adaptés au contexte local : connectivité variable, smartphones d'entrée de gamme, économie largement informelle, forte culture de solidarité communautaire (tontines), et un accès au crédit encore limité malgré une adoption massive du paiement mobile.

## 🌍 Pourquoi maintenant, pourquoi ici

- La Côte d'Ivoire compte plus de 25 millions de comptes mobile money actifs, avec un taux d'adoption parmi les plus élevés au monde (~89%, GSMA).
- Le taux d'inclusion financière globale atteint 58% (Banque mondiale, Global Findex 2025), porté presque entièrement par le mobile money — alors que le taux de bancarisation strict reste à ~31%. C'est ce décalage qui crée l'opportunité : l'accès existe, l'usage utile (crédit, épargne structurée, fidélisation) reste à construire.
- Le gouvernement ivoirien a fait de la transformation numérique une priorité nationale : cinq axes stratégiques pour 2026 (connectivité, paiements numériques, compétences numériques, cybersécurité, innovation), un budget ministériel en hausse de 37%, et une ambition de gouvernement "zéro papier" à horizon 2030.
- Le secteur de la microfinance ivoirien connaît une croissance rapide (2,9 millions de clients au T1 2026, +14,3% en un trimestre), mais reste concentré à Abidjan et peu adapté aux petits commerçants et à l'agriculture.

## 🧩 Premier produit : application de fidélité pour commerçants

Le premier projet de l'écosystème est une **application de fidélité client pour les retailers indépendants** (maquis, pharmacies, petites boutiques, supermarchés de proximité) en Côte d'Ivoire.

**Le problème** : les petits commerçants n'ont pas les moyens de développer leur propre programme de fidélité (contrairement aux grandes enseignes comme Carrefour), alors que la fidélisation client est un levier direct de chiffre d'affaires.

**La solution** : une app légère (QR code / numéro de téléphone) qui permet à un commerçant d'offrir un programme de points à ses clients, avec :
- Un système de points configurable par commerçant
- Une carte de fidélité digitale pour le client (remplace la carte à tampons papier)
- Des notifications par SMS/WhatsApp (plus fiables que le push notification dans ce contexte)
- Un tableau de bord simple pour le commerçant
- *(v2)* Conversion des points en cash-out via mobile money — la fonctionnalité différenciante par rapport aux solutions de fidélité occidentales, rendue possible par la maturité du mobile money local

**Modèle économique** : abonnement mensuel par commerçant (SaaS), payé en mobile money, avec des paliers selon le volume de clients actifs.

### 📱 L'application client : le quotidien, dans la poche

La fidélité ne fonctionne que si le client a une raison d'ouvrir l'app chaque jour. L'application client (`djassa-App-user`) est donc pensée comme un outil du quotidien, pas comme une simple carte de points :

- **Trouver un maquis** : recherche par plat (poulet braisé, garba, alloco…), par nom ou par commune.
- **Pharmacies de garde** : la liste des pharmacies de garde en ce moment, avec la fin de la garde et un bouton « Appeler ». Aucune API officielle n'existe : la rotation hebdomadaire est saisie par un administrateur depuis la liste officielle publiée.
- **Payer** : le client paie un maquis ou une pharmacie depuis son portefeuille mobile money (Wave, Orange Money, MTN MoMo, Moov Money), via l'agrégateur agréé. **L'argent va directement du portefeuille du client à celui du commerçant — Djassa ne le détient jamais**, conformément à [`dkassa-inclusion-financiere.md`](./dkassa-inclusion-financiere.md). L'app le dit au client au moment de payer.
- **Fidélité** : chaque paiement réussi rapporte des points chez ce commerçant (taux configurable par commerçant) ; les points s'échangent contre des récompenses offertes par ce même commerçant (boisson, remise, livraison). **Pas de conversion en argent** tant que le cadre BCEAO n'est pas validé.

Le paiement est ce qui rend l'app essentielle : c'est le geste qui génère à la fois les points du client et l'historique vérifié du commerçant.

📄 Voir [`docs/loyalty-app.md`](docs/loyalty-app.md) pour le détail du MVP, du modèle de pricing et du plan pilote *(à créer)*.

## 🗺️ Roadmap de l'écosystème

L'application de fidélité est une porte d'entrée, pas une fin en soi. Elle génère un historique de transaction et de comportement client qui peut alimenter les projets suivants :

| # | Domaine | Idée d'application | Lien avec le projet 1 |
|---|---|---|---|
| 1 | Commerce & fidélité | App de fidélité multi-commerçants (MVP en cours) | — |
| 2 | Inclusion financière | Scoring crédit basé sur l'historique mobile money / fidélité, pour débloquer du micro-crédit ou du paiement différé chez les commerçants partenaires | Réutilise directement les données du projet 1 |
| 3 | Inclusion financière | Digitalisation des tontines (épargne rotative communautaire) : suivi des cotisations, rappels automatiques, paiement mobile money | Marché commun, socle technique partagé (paiement mobile) |
| 4 | Agriculture | Traçabilité et accès marché pour petits producteurs (cacao, anacarde), avec paiement direct via mobile money | Même logique d'intégration mobile money |
| 5 | Services publics | Application d'accompagnement aux démarches administratives en ligne, en appui à la stratégie nationale "zéro papier" | Aligné avec les priorités gouvernementales identifiées |
| 6 | Éducation financière | Module gamifié d'éducation financière, intégrable dans les projets 1 à 3 | Composant transverse, pas un produit autonome |

*Cette roadmap est indicative — chaque produit sera validé indépendamment par un pilote terrain avant tout investissement de développement significatif.*

## 🏗️ Principes de conception transverses

Tous les produits de cet écosystème partagent les mêmes contraintes et choix de conception :

- **Mobile money natif** : intégration via un agrégateur (ex. CinetPay) pour couvrir Wave, Orange Money, MTN MoMo et Moov Money en une seule API, plutôt que des intégrations séparées.
- **Low-bandwidth first** : conception pensée pour la 3G/4G instable et les smartphones d'entrée de gamme ; privilégier le web léger, le PWA ou le SMS/WhatsApp plutôt que des apps natives lourdes, au moins en phase de validation.
- **SMS/WhatsApp avant push notification** : plus fiable et plus universellement adopté dans le contexte local.
- **Alignement avec les priorités publiques** : chaque produit est pensé pour s'inscrire dans un axe déjà identifié comme prioritaire par le gouvernement ou les acteurs institutionnels (APIF, ministère de la Transition numérique), afin de faciliter d'éventuels partenariats.
- **Validation terrain avant scale** : chaque produit démarre par un pilote restreint (5-10 utilisateurs/commerçants) avant tout développement supplémentaire.

## 📌 Statut actuel

- [x] Étude de marché initiale (mobile money, paysage concurrentiel, priorités gouvernementales)
- [x] Définition du MVP et du modèle de pricing pour le projet 1 (fidélité)
- [ ] Choix du nom de marque définitif
- [ ] Développement du MVP
- [ ] Pilote terrain (Abidjan, 5-10 commerçants)
- [ ] Itération et décision de scale

## 📝 Licence

*(à définir)*

## 📬 Contact

*(à compléter)*

