# Handoff batch 4 - stage 2, the widening

Seat: @builder
Repository: /Users/aashanjaved/band-work/result

Parent revision: 0952b5451558896c838d6146ae27e87388918fca     - NOT the submitted revision
Submitted revision: derive with `git log -1 --format=%H -- handoffs/batch-4.md`

Both lines adjacent, per the amended section 13. The parent is what I could
know at write time; a file cannot name the commit that contains it.

## Blobs under test

    stage-2/Dockerfile     5d070e3f9d0cf833e476d1ec952a0f157a46469f
    stage-2/RUN.md         a460ecfe6b104efcefd9cf3a06f223fdab3ec32f
    stage-2/app.py         8a9182454355c789d6ca8380b80da4b6b58235f4

stage-1/ is untouched throughout stage 2 and stays byte-identical to the
revision it was audited at.

## Claims submitted (58)

Every remaining stage-2 claim. S-0 is already settled PASS.

    S-1 .. S-58

## Check anchors (sections 11 and 13)

sha256 of the canonical Check form, with its byte count beside it.
DETECTION, NOT PREVENTION: a mismatch means the Check moved between my read
and your run. It does not stop it moving, and a passing batch is not evidence
that F-11 is closed.

    S-1    a2bb620b21cc3ae901f8ff513f2846b20563edfdfc6158829bc94b1cbcfe5872  948
    S-2    a18fe3dad0b366e75150cb4632962984537b1f85e5885c3d840e9ebf936173ae  672
    S-3    119fa2b40c18583f48218aeefef9ad906dfbf1b79212f43b143d583cd342f9c0  583
    S-4    d07c375baa19b6d183f2965912c46c8c012c19814d58eed6081de4522762e512  535
    S-5    e8829613e116ac639656010a9c9778c38bcfe55c7554230e53953c5ca6698f2e  862
    S-6    843040a498a9af18ff0e1e9e80616a2d6f42e4416a4c58f84f4fd3050ad1de85  1072
    S-7    6ec421978c753d35586792a073d3c10c0cbbcdc9d66efb7d1d844362e2921a6b  525
    S-8    4f977b7c919ca572747f90b610d578f7962791aac271456df05242bba35e7633  285
    S-9    320603f31e995e25f4a32b5026683a77e358b4a36c973f2f8eda4c2bd9bb1e9d  284
    S-10   e1f34a553a1f209fb8d3f4dc54334c736f0731a028ae6b1c85b84a46c7bb53fa  351
    S-11   dce29c772aee222a4b0242f6065d638cfff0e8d7e45b33b8934fbeaa7d99c31b  339
    S-12   7e1de776708674066e86e6c2987245f268431f206afa3377f8539622e7180c1d  431
    S-13   4c7cf8d7a79ef6ea96f5322cd53fae8ea413c814035d60a2c689196185438452  212
    S-14   b2f97abaddd5c0405af5aa33587285f201a48b38c8c8951610dfc8c1f5a329c2  545
    S-15   755d634c10e19effe06f0baadb492597e30e657b1515ad3aeeaecea23c198e28  672
    S-16   16b8d2cd8c825758fc4fc31c943d2e1b9350815613491b8e614e785aedf509fa  262
    S-17   f8214ae7ad9332a9a3745b546be84d287e7e6b707031ae00e15f1e05556c485f  400
    S-18   33ba689b5e34ebc9db332b2034395685797b79ac1463c6933b90a62a09654d15  322
    S-19   ca2701cd845ee81a019a3e700bccc743ae3ab30f7314cc1fb13365044029ddfd  406
    S-20   e2b081b5fdf9e4678e2966af20a09da7bd5ef79c5c205380ca1a523ffa93b2a0  347
    S-21   12eb54bb3919d8b13053fbc3d8943cd904029af82de597b0d34851237d6f3b37  432
    S-22   bec5dd8981217e7f97c43c7c74c42be184d76cf2913d4a8f29a181d8b21284cd  787
    S-23   0e29f67e176fa7a1ee13d3983e093d9afbd8fca6ffd9b463bea189c61390356f  646
    S-24   042e27d93b2214efbc0640a8fc1c48aad700b79e7916e674386ca58e4e914515  851
    S-25   55f6b3d8ff38fefd2e557ab8e875540c2d0099ab6f61f2ada8d5dd3b41c42c98  517
    S-26   20a16074ed36bbff95f3ec83c52e9fafa08d54275a71a58248383eae7d88ca77  1083
    S-27   3707d488d964204d3fd72af828032870ee3051b614a49858ab59ad565490b118  922
    S-28   00de6822b811856930cb1bae4e8040843cb2a17dad0e25c9d828227dcce6d51d  540
    S-29   47287b08c767067d74567755dbdfcc2e4fd83c1ad191bbe84a1dbaa591c51348  655
    S-30   ee3f355d4effb105490751071bada3606bb8667999fce835549d0e57c89733e0  636
    S-31   65cf13eecde07618bcb02cffc69f8387a3d48ecd5df6ce70b8eb3c92ca394ea7  743
    S-32   1d6eabe69130758830e4344c2b2d628027730f373864496acb75088f62c59056  627
    S-33   b28d0500881ea6d60d620e48612357c6d7a5b5e0c6307fbbe49a722d87e15517  396
    S-34   61f83e619101bdc3849999ccae9e23c14de0a80d46680b38eef5c7a530eca128  638
    S-35   1746f067372e8b093e54552aa4731bbffb5e824b3b504a54f241d46ef6c79f82  763
    S-36   70b60ac56f3ad0781b43d48eb268638e28ebed3a1bd92fea2bb23e05ceac4f8b  393
    S-37   bbfe4324e1a9c43fa420fdb8dd67e27f00940ecf8cc6913cd7d3816cb2a74fbc  853
    S-38   f32860dc3b0070fb9d33631bffabdcef083e723c40d3b8b8b31a0bb1353e768b  752
    S-39   7f2ac32260744816c92c7c97c73d6e80eb6a92ae28992d6028607b5065f14c2a  860
    S-40   f4f1330031634b41e549d0b0fa8da21103c0b66790111468bc979279b68d2e94  801
    S-41   288160d243ddd55c955e654b74d9a3a589e308dae39409119008489434c5932d  790
    S-42   9f2d18d468fb8ea102a8dbaa383aabdb06f536f7aa408bc755aa5e26f2521c6a  949
    S-43   4ce20eb11560f878a1bf3bae6843bd26756d99be45fd52c8e1532c016733f12d  1180
    S-44   c879574c7101a79ed6d6a3f29ae7ed13fdca8c309d3fd5505ee61c1fbed97067  1766
    S-45   e977720e03a47272b0ecff7b38c4203696bd243ab396be694290916f9d420ffd  1127
    S-46   db66ecb375ab99c7bb74ebbeec7e2ef35ef1a26f2c4fa93a2b362c8105f85970  2762
    S-47   d6a40bdddc8279300b7e0b5be74d1c0683403fa32d7f70d507cdc5ce0d5943e2  2270
    S-48   eae87e6f6389f14d1df8895c890f0de613abaa6bbc4b72a2cf332a38e87181b5  2939
    S-49   fdc679d0ca3b8d85e9695828689484124ea3cafec96ec66f4a8f54af958f7bf6  929
    S-50   c5583bdc05fe9e547c1549aaea7b05d0d96c52dc7da94994f1493af099e6f36e  2394
    S-51   70a5548daa10f1dd608e0c7ebd306ac07c4324ec948f9f3033f25db7e9c45577  1479
    S-52   1c51031ef8b922f9cc699bdaf1c3c37bfbd2adbd4a552195fb9f45ef79be35b9  660
    S-53   1a0a1f04daa5e4eaf1c2d81838a9a1ef991cedf43a8fee0373b82ad3d28b69a6  2073
    S-54   bee4dec26ced511a7e8a1639ffad54b7e7f98c2bb5fb2f116cdefe9cb1ec6255  965
    S-55   125a93ef9c338e9f953c1a904473d02ec2c4bbd342ea978ec0f89bcf8e3e963f  1343
    S-56   58416ab4391451b76b1d50f1435b15e37a9cf7b2286112d0c160143bf6d43a76  1991
    S-57   59f823613fb637bee138f50bee06284d2f9e356a5009cae8823e41db0fdf4611  1256
    S-58   89b4fb334f885efd5645ebe7ba1a01208995f5f666137fee5cce9e35a4f40ccd  1160

## What I ran myself

Not evidence. Your runs settle these.

    53 of 59 passed. The 6 failures are reported below as check defects.
    S-1  no egress, sibling alpine probe        {"status": "ok"} NO EGRESS
    S-2  RUN.md's own command                   RUNMD OK AT <revision>
    S-3  graded suites 1 AND 2, isolated        stage 1: pass, stage 2: pass
         120 passed / 25 passed, claimed_stage 2, share 1.0, stage 3 fails as required
    S-48 real stage-1 image -> real stage-2 image   UPGRADE OK <reference>
    S-4..S-40, S-42..S-46, S-52..S-57           all printed PASS

## Six claims I expect to FAIL, submitted anyway

    S-41, S-47, S-49, S-50, S-51, S-58

Omitting a claim settles it by assurance, which I was refused for in stage 1.
All six EXECUTE and FAIL rather than erroring, except S-47 and S-50 which
raise inside the check's own code. Each is a defect in the Check, not in the
implementation, and each is reproduced from a run in the room message.

  S-47, S-50  `await br.close()` precedes `await ref.inner_text()` in the
              check's own return statement, so reading the confirmation always
              raises TargetClosedError. S-46 has the same body with the close
              AFTER the read and passes. Unsatisfiable as written.

  S-41        changes only booking-party-size and resubmits, so the second
              booking targets the SAME table and slot its own first booking
              holds. Two overlapping confirmed bookings on one table is what
              section 1 forbids and stage 1's C-47 asserts is 409.

  S-51        books t_3 at 19:00 through the browser, then requires a second
              account to book t_3 at 19:00 with 201 to produce the refused
              style. That table is taken by the browser's own booking.

  S-58        books the t_1+t_2 pair through the API, then requires the browser
              to select the t_1+t_2 cell. available_options is empty for that
              slot afterwards, so the cell is correctly unavailable and inert.

  S-49        exports BEFORE the browser logs in, so the browser's token is not
              in the snapshot; the import then replaces all credentials, which
              section 10 requires and stage 1's C-112 asserts. S-48 models the
              upgrade correctly with two images and passes.

## One real defect this batch found in my code

S-48 failed first time: a stage-1 snapshot records one `table_id` per
reservation, and importing it produced a reservation with no table set,
surfacing as 422 on the next read of a retained reference. Fixed - import maps
a legacy table_id to a one-member table_ids. That claim is the only one that
exports from a real stage-1 image into a real stage-2 image, and it is the only
thing that would have caught it.

## Section 8

Lock ACQUIRED before every Docker command and RELEASED after. Docker left
clear: no tk-* containers, no tk-* networks, nothing on 18080.
