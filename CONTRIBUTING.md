# 🤝 Contribuer à MonPetitMaraicher

Merci de vouloir contribuer ! Ce projet est porté par et pour les
**producteurs indépendants** et les personnes qui veulent renforcer les
circuits courts. Toutes les contributions sont bienvenues : code, tests,
documentation, design, retours terrain de maraîchers et de clients.

## Licence

En contribuant, vous acceptez que vos contributions soient publiées sous
la licence **GNU AGPL-3.0** (voir [LICENSE](LICENSE)).

## Comment contribuer

1. Forkez le projet puis créez une branche :
   `git switch -c feat/ma-fonctionnalite`
2. Faites vos modifications, en respectant la convention de nommage des
   branches : `feat/…`, `fix/…`, `doc/…`
3. Vérifiez que le projet démarre :
   ```bash
   python manage.py check
   ```
4. Ouvrez une Pull Request décrivant :
   - le problème ou besoin résolu,
   - ce que fait votre modification,
   - comment la tester (étapes concrètes).

## Principes du projet

- **Sobriété** : stack simple, dépendances minimales, hébergeable partout
  (petits hébergeurs, AlwaysData, Raspberry Pi…).
- **Indépendance des producteurs** : chaque maraîcher reste maître de ses
  données, de ses prix et de son fonctionnement ; le portail est un outil,
  pas un intermédiaire commercial.
- **Réplicabilité** : toute personne doit pouvoir déployer sa propre
  instance pour sa zone/département.
- **Accessibilité** : interfaces sobres, légères, utilisables sur mobile.

## Signaler un problème

Ouvrez une *issue* en décrivant :
- le contexte (maraîcher / client / administrateur, navigateur),
- les étapes pour reproduire,
- le comportement attendu.

## Contact

Pour les questions d'orientation du projet, ouvrez une *issue* étiquetée
« discussion ».
