# Publishing the apps on Google Play

Two apps, one Play Console account:

| App | Package (permanent once published) | Repository |
|---|---|---|
| Fidelia (customers) | `ci.fidelia.fidelia_user` | fidelia-App-user |
| Fidelia Pro (merchants) | `ci.fidelia.fidelia_merchant` | fidelia-App-retailer |

Both target Android 16 (API 36), which Play requires for new apps and updates
since 31 August 2026.

## 1. Signing: keep one key for Play and the website

The APKs on the website's `/app` page are signed with the release key stored
in the GitHub secrets (`ANDROID_KEYSTORE_BASE64` and friends). Android only
installs an update signed with the same key as the installed app, so:

* In Play Console → the app → **Test and release → App integrity → App
  signing**, choose **Use a different key / Export and upload a key from Java
  keystore**, and upload **that same release key** (Play gives the PEPK tool
  and the exact command). Play then signs installs with your key, and a phone
  can move between the website APK and the Play version without uninstalling.
* If Play generates its own key instead, the two versions cannot update each
  other: a tester must uninstall the website APK (and lose unsynced data)
  before installing from Play.
* The upload key is the same file. Keep the keystore and its passwords in the
  team's password manager: without them no update can ever be published.

## 2. Build what Play takes

Each tagged release (`git tag v0.2.0 && git push origin v0.2.0`) builds the
APKs **and** the app bundle. The bundle is in the workflow run's artifacts as
`play-bundle-<version>-<number>` (`app-release.aab`), never in the public
release. The version code is the run number, so it always increases, which
Play requires.

Locally: `scripts/build-release.sh <https api>` builds both (needs
`android/key.properties`).

The API address baked into the build is the repository variable
`FIDELIA_API_BASE` (today the test API). Before a public production release,
point it at the production API and tag a new version.

## 3. Create each app

Play Console → **Create app**: name *Fidelia* / *Fidelia Pro*, default language
**French – fr-FR**, **App**, **Free**. Accept the declarations.

Start with **Test and release → Testing → Closed testing** (or Internal
testing for the team): upload the `.aab`, add testers by email list, and share
the opt-in link on WhatsApp. A personal developer account needs **12 testers
opted in for 14 days** in a closed test before production access; the pilot
merchants, cashiers and team are those testers.

## 4. Store listing

Everything is in each app repository under
`android/fastlane/metadata/android/fr-FR/`:

| Field | File | Limit |
|---|---|---|
| App name | `title.txt` | 30 |
| Short description | `short_description.txt` | 80 |
| Full description | `full_description.txt` | 4000 |
| App icon (512 × 512, 32-bit PNG) | `images/icon.png` | |
| Feature graphic (1024 × 500) | `images/featureGraphic.png` | |
| Release notes | `changelogs/default.txt` | 500 |

`scripts/make-icons.py` redraws the icon and feature graphic with the launcher
icons. Still needed: **2 to 8 phone screenshots** (PNG or JPEG, each side
between 320 and 3840 px, the long side at most twice the short side; a
1080 × 2400 capture must be cropped to 1080 × 2160).

Category: Fidelia → *Shopping*; Fidelia Pro → *Business*. Contact email: the
team's address (shown publicly).

## 5. App content (Policy → App content)

| Form | Answer |
|---|---|
| Privacy policy | URL of the published policy (to do, see § 6) |
| App access | Restricted: give reviewers a test number and its code. On the test API, `07 00 00 00 01` (customer) and `07 00 00 00 02` (merchant) sign in with `000000`. |
| Ads | No ads |
| Content rating | Questionnaire: reference / utility app; no violence, sexuality, gambling, drugs; users do not chat. Shops publish photos and deals reviewed by the team. |
| Target audience | 18 and over |
| News app | No |
| Government app | No |
| Financial features | Declare: *payments* (the customer pays the merchant from their own mobile wallet; Fidelia holds no money) and, for layaway, *other*: "paiement d'un produit en plusieurs versements au commerçant, sans crédit, intérêts ni frais". Never describe it as credit or a loan. |
| Health | No |
| Account deletion | URL where anyone can ask for deletion, plus the in-app path (to do, see § 6) |

### Data safety

All data goes over HTTPS to Fidelia's own API. No advertising or analytics
SDK. Not sold. Not shared with third parties for their own use (the SMS
provider and Wave act on Fidelia's or the user's behalf, which Play does not
count as sharing).

| Data type | Fidelia (customer) | Fidelia Pro (merchant) | Purpose | Optional? |
|---|---|---|---|---|
| Phone number | Collected | Collected (owner, cashiers, and the customer numbers they enter with consent) | Account management, app functionality | Required |
| Name | No | Collected (contact name on a partner request) | Account management | Required for the request |
| Purchase history | Collected (payments, points, layaway) | Collected (the shop's sales) | App functionality | Required |
| Precise location | No | Collected (the shop's position, when the merchant sets it) | App functionality | Optional |
| Photos and videos | No | Collected (shop photos and videos) | App functionality | Optional |
| App interactions | Collected (screen views, random install id, no phone number) | Collected | Analytics | Required |
| Crash logs, diagnostics | Collected (no phone numbers) | Collected | Analytics, app functionality | Required |

Encrypted in transit: yes. Users can request deletion: yes, once § 6 exists.

The customer app scans QR codes with Google ML Kit, bundled on the phone.
Check ML Kit's own data disclosure page before submitting and add what it
lists (it may report diagnostics to Google).

## 6. Before the first review

1. **Account deletion** (Play requirement for apps that create accounts): a
   *Supprimer mon compte* path in both apps, and a public web page where
   anyone can ask for it without the app.
2. **Privacy policy** page, public, in French, matching the ARTCI declaration
   and the Data safety answers above.
3. **Screenshots**: 2 to 8 per app (§ 4).
4. **Signing key** uploaded as in § 1.
